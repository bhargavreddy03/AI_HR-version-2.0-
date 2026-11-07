"""Authentication, session coordination, and identity lifecycle service layer."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import generate_uuid7, utc_now
from app.core.config import Settings
from app.core.errors import (
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
    RateLimitException,
    ValidationException,
)
from app.core.redis import RedisClient
from app.core.security import hash_password, needs_rehash, verify_password
from app.modules.auth.crypto import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_backup_codes,
    generate_csrf_token,
    generate_secure_token,
    generate_totp_secret,
    get_totp_uri,
    hash_backup_code,
    hash_token,
    verify_backup_code,
    verify_totp,
)
from app.modules.auth.jwt import (
    create_access_token,
)
from app.modules.auth.models import (
    AuthRevocationOutbox,
    CandidateUserProfile,
    User,
    UserSession,
)
from app.modules.auth.redis_session import (
    check_and_record_totp_code,
    check_rate_limit,
    delete_all_user_sessions_monotonic,
    delete_session,
    set_version_fences_if_absent,
    store_session,
)
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.modules.organizations.models import (
    Organization,
    OrganizationMembership,
    Permission,
    RolePermission,
)

logger = logging.getLogger(__name__)


async def resolve_user_permissions(db: AsyncSession, role_id: UUID) -> list[str]:
    """Load active capability codes associated with a specific role."""
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def register_user(
    db: AsyncSession,
    request: RegisterRequest,
    settings: Settings,
) -> User:
    """Register a new global user identity and default candidate portfolio profile."""
    # Check email uniqueness (normalized lowercase)
    stmt = select(User).where(func.lower(User.email) == request.email.lower())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise ConflictException(
            "An account with this email address already exists",
            error_code="ACCOUNT_ALREADY_EXISTS",
        )

    # Hash password with Argon2id conforming to memory >= 64MB
    hashed = hash_password(request.password, settings=settings)

    user_id = generate_uuid7()
    user = User(
        id=user_id,
        email=request.email.lower(),
        password_hash=hashed,
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        phone_number=request.phone_number.strip() if request.phone_number else None,
        token_version=1,
        is_active=True,
        is_super_admin=False,
    )
    db.add(user)

    # Automatically create platform-global Candidate-Owned Profile (Architecture Document 05 Table 3)
    candidate_profile = CandidateUserProfile(
        user_id=user_id,
        headline=None,
        bio=None,
        portfolio_urls=[],
        self_declared_skills=[],
    )
    db.add(candidate_profile)

    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession,
    redis: RedisClient,
    login_data: LoginRequest,
    client_ip: str | None,
    user_agent: str | None,
    settings: Settings,
) -> tuple[dict[str, Any] | None, str | None, UserResponse | None]:
    """Authenticate credentials, enforce rate limits, handle MFA challenges, and issue session.

    Returns:
    - (auth_result_dict, None, None) on full success
    - (None, mfa_challenge_token, user_summary) if MFA verification is required
    """
    # 1. Brute-force protection in Redis
    ip_identifier = client_ip or "unknown_ip"
    within_limit = await check_rate_limit(
        redis,
        identifier=f"{ip_identifier}:{login_data.email.lower()}",
        action="login",
        max_attempts=5,
        window_seconds=60,
    )
    if not within_limit:
        raise RateLimitException(
            "Too many failed login attempts. Please wait 60 seconds before trying again.",
            error_code="RATE_LIMIT_EXCEEDED",
        )

    # 2. Query user by email
    stmt = select(User).where(func.lower(User.email) == login_data.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash, settings=settings):
        # Generic authentication failure to prevent account enumeration
        raise AuthenticationException(
            "Invalid email or password",
            error_code="INVALID_CREDENTIALS",
        )

    # 3. Check account activation
    if not user.is_active:
        raise AuthenticationException(
            "Account has been suspended or deactivated",
            error_code="ACCOUNT_DEACTIVATED",
        )

    # 4. Optional hash migration if parameters have updated
    if needs_rehash(user.password_hash, settings=settings):
        user.password_hash = hash_password(login_data.password, settings=settings)
        await db.commit()

    # 5. Check MFA requirement
    if user.mfa_enabled and user.mfa_secret:
        # Create temporary MFA challenge token stored in Redis with 5 min TTL
        challenge_token = generate_secure_token(32)
        challenge_data = {
            "user_id": str(user.id),
            "organization_slug": login_data.organization_slug,
            "ip": client_ip,
            "user_agent": user_agent,
            "token_version": user.token_version,
        }
        import json

        await redis.set(f"mfa_challenge:{challenge_token}", json.dumps(challenge_data), ex=300)

        user_summary = UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            active_tenant_id=None,
            role=None,
            permissions=[],
            mfa_enabled=True,
            is_active=user.is_active,
        )
        return None, challenge_token, user_summary

    # 6. Issue full session
    auth_result = await create_authenticated_session(
        db=db,
        redis=redis,
        user=user,
        organization_slug=login_data.organization_slug,
        client_ip=client_ip,
        user_agent=user_agent,
        settings=settings,
    )
    return auth_result, None, None


async def create_authenticated_session(
    db: AsyncSession,
    redis: RedisClient,
    user: User,
    organization_slug: str | None,
    client_ip: str | None,
    user_agent: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Create session in PostgreSQL & Redis and return access, refresh, and CSRF tokens."""
    tenant_id: UUID | None = None
    role_name: str | None = None
    role_id: UUID | None = None
    role_version: int = 1
    permissions: list[str] = []

    # Resolve organization context if slug provided, or fall back to user's first active membership
    if organization_slug:
        org_stmt = select(Organization).where(
            Organization.slug == organization_slug.strip().lower()
        )
        org = (await db.execute(org_stmt)).scalar_one_or_none()
        if not org or org.status != "active":
            raise AuthorizationException(
                "Requested organization not found or is suspended",
                error_code="ORGANIZATION_UNAVAILABLE",
            )
        tenant_id = org.id

        mem_stmt = (
            select(OrganizationMembership)
            .options(selectinload(OrganizationMembership.role))
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        membership = (await db.execute(mem_stmt)).scalar_one_or_none()
        if not membership:
            raise AuthorizationException(
                "You do not hold an active membership in this organization",
                error_code="MEMBERSHIP_REQUIRED",
            )
        role_name = membership.role.name
        role_id = membership.role_id
        role_version = membership.role_version
        permissions = await resolve_user_permissions(db, role_id)
    else:
        # Check if user has active memberships
        mem_stmt = (
            select(OrganizationMembership)
            .options(
                selectinload(OrganizationMembership.role),
                selectinload(OrganizationMembership.organization),
            )
            .where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_active.is_(True),
            )
            .order_by(OrganizationMembership.created_at.asc())
        )
        first_mem = (await db.execute(mem_stmt)).scalars().first()
        if first_mem and first_mem.organization.status == "active":
            tenant_id = first_mem.tenant_id
            role_name = first_mem.role.name
            role_id = first_mem.role_id
            role_version = first_mem.role_version
            permissions = await resolve_user_permissions(db, role_id)
        else:
            role_name = "candidate"
            permissions = ["candidate:profile:manage"]

    session_id = generate_uuid7()
    refresh_token = generate_secure_token(48)
    refresh_token_hash = hash_token(refresh_token)
    csrf_token = generate_csrf_token()

    now = utc_now()
    refresh_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # 1. Persist UserSession in PostgreSQL
    db_session = UserSession(
        id=session_id,
        user_id=user.id,
        tenant_id=tenant_id,
        refresh_token_hash=refresh_token_hash,
        token_version=user.token_version,
        ip_address=client_ip[:45] if client_ip else None,
        user_agent=user_agent[:512] if user_agent else None,
        is_revoked=False,
        expires_at=refresh_expires_at,
    )
    db.add(db_session)
    user.last_login_ip = client_ip[:45] if client_ip else None
    await db.commit()

    # 2. Persist Session & Version Fences in Redis (Architecture Document 07)
    session_data = {
        "session_id": str(session_id),
        "user_id": str(user.id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role_name,
        "token_version": user.token_version,
        "role_version": role_version,
        "user_status": user.is_active,
        "membership_active": True,
        "last_db_verified_at": now.timestamp(),
        "created_at": now.timestamp(),
    }
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await store_session(redis, user.id, session_id, session_data, ttl_seconds=ttl_seconds)
    await set_version_fences_if_absent(
        redis,
        user_id=user.id,
        token_version=user.token_version,
        tenant_id=tenant_id,
        role_version=role_version,
    )

    # 3. Create short-lived JWT Access Token
    access_token = create_access_token(
        user_id=user.id,
        session_id=session_id,
        tenant_id=tenant_id,
        role=role_name,
        permissions=permissions,
        token_version=user.token_version,
        role_version=role_version,
        is_super_admin=user.is_super_admin,
        settings=settings,
    )

    user_response = UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        active_tenant_id=tenant_id,
        role=role_name,
        permissions=permissions,
        mfa_enabled=bool(user.mfa_enabled),
        is_active=bool(user.is_active),
    )

    return {
        "user": user_response,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "csrf_token": csrf_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def verify_mfa_challenge(
    db: AsyncSession,
    redis: RedisClient,
    challenge_token: str,
    code: str,
    settings: Settings,
) -> dict[str, Any]:
    """Verify MFA challenge code and issue full authenticated session."""
    import json

    challenge_raw = await redis.get(f"mfa_challenge:{challenge_token}")
    if not challenge_raw:
        raise AuthenticationException(
            "MFA challenge has expired or is invalid. Please log in again.",
            error_code="MFA_CHALLENGE_EXPIRED",
        )

    challenge_data = json.loads(challenge_raw)
    user_id = UUID(challenge_data["user_id"])

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not user.is_active or not user.mfa_secret:
        raise AuthenticationException("Invalid authentication state", error_code="INVALID_STATE")

    # Replay check for code
    clean_code = code.strip().replace("-", "").upper()
    is_fresh = await check_and_record_totp_code(redis, user.id, clean_code)
    if not is_fresh:
        raise AuthenticationException(
            "MFA code has already been used", error_code="MFA_CODE_REPLAYED"
        )

    # Decrypt TOTP secret and verify
    totp_secret = decrypt_mfa_secret(user.mfa_secret, settings.JWT_SECRET_KEY)
    totp_valid = verify_totp(totp_secret, clean_code)

    if not totp_valid:
        # Check backup codes if available
        matched_idx = -1
        if user.mfa_backup_codes:
            matched_idx = verify_backup_code(clean_code, user.mfa_backup_codes)
        if matched_idx >= 0:
            # Consume single-use backup code
            codes = list(user.mfa_backup_codes or [])
            codes.pop(matched_idx)
            user.mfa_backup_codes = codes
            await db.commit()
        else:
            raise AuthenticationException(
                "Invalid MFA verification code", error_code="MFA_INVALID_CODE"
            )

    # Delete challenge from Redis
    await redis.delete(f"mfa_challenge:{challenge_token}")

    return await create_authenticated_session(
        db=db,
        redis=redis,
        user=user,
        organization_slug=challenge_data.get("organization_slug"),
        client_ip=challenge_data.get("ip"),
        user_agent=challenge_data.get("user_agent"),
        settings=settings,
    )


async def refresh_session_tokens(
    db: AsyncSession,
    redis: RedisClient,
    refresh_token_str: str,
    client_ip: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Execute refresh token rotation and issue fresh credentials.

    Enforces refresh token reuse detection and session validation.
    """
    token_hash = hash_token(refresh_token_str)
    stmt = (
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(UserSession.refresh_token_hash == token_hash)
    )
    session_rec = (await db.execute(stmt)).scalar_one_or_none()

    if not session_rec:
        raise AuthenticationException(
            "Session not found or invalid refresh token",
            error_code="SESSION_INVALID",
        )

    # Reuse Detection: If an already revoked session is presented, invalidate immediately
    if session_rec.is_revoked:
        logger.warning(
            "Detected refresh token reuse for session %s, user %s",
            session_rec.id,
            session_rec.user_id,
        )
        await delete_session(redis, session_rec.user_id, session_rec.id)
        raise AuthenticationException(
            "Refresh token has been revoked",
            error_code="SESSION_REVOKED",
        )

    now = utc_now()
    if session_rec.expires_at < now:
        session_rec.is_revoked = True
        await db.commit()
        await delete_session(redis, session_rec.user_id, session_rec.id)
        raise AuthenticationException("Session has expired", error_code="SESSION_EXPIRED")

    user = session_rec.user
    if not user.is_active:
        session_rec.is_revoked = True
        await db.commit()
        await delete_session(redis, user.id, session_rec.id)
        raise AuthenticationException("Account is deactivated", error_code="ACCOUNT_DEACTIVATED")

    # Check token version fence in PostgreSQL
    if user.token_version != session_rec.token_version:
        session_rec.is_revoked = True
        await db.commit()
        await delete_session(redis, user.id, session_rec.id)
        raise AuthenticationException(
            "Token version mismatch; session invalidated",
            error_code="TOKEN_VERSION_MISMATCH",
        )

    # Resolve active tenant and permissions
    tenant_id = session_rec.tenant_id
    role_name = "candidate"
    role_version = 1
    permissions = ["candidate:profile:manage"]

    if tenant_id:
        mem_stmt = (
            select(OrganizationMembership)
            .options(
                selectinload(OrganizationMembership.role),
                selectinload(OrganizationMembership.organization),
            )
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        membership = (await db.execute(mem_stmt)).scalar_one_or_none()
        if not membership or membership.organization.status != "active":
            # Demote to non-tenant session if membership was terminated
            tenant_id = None
            session_rec.tenant_id = None
        else:
            role_name = membership.role.name
            role_version = membership.role_version
            permissions = await resolve_user_permissions(db, membership.role_id)

    # Rotate refresh token (Generate fresh cryptographic string and update hash)
    new_refresh_token = generate_secure_token(48)
    new_csrf_token = generate_csrf_token()
    session_rec.refresh_token_hash = hash_token(new_refresh_token)
    session_rec.expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session_rec.ip_address = client_ip[:45] if client_ip else session_rec.ip_address
    await db.commit()

    # Update session in Redis
    session_data = {
        "session_id": str(session_rec.id),
        "user_id": str(user.id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role_name,
        "token_version": user.token_version,
        "role_version": role_version,
        "user_status": user.is_active,
        "membership_active": True,
        "last_db_verified_at": now.timestamp(),
        "created_at": (
            session_rec.created_at.timestamp() if session_rec.created_at else now.timestamp()
        ),
    }
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await store_session(redis, user.id, session_rec.id, session_data, ttl_seconds=ttl_seconds)

    # Issue fresh short-lived JWT Access Token
    access_token = create_access_token(
        user_id=user.id,
        session_id=session_rec.id,
        tenant_id=tenant_id,
        role=role_name,
        permissions=permissions,
        token_version=user.token_version,
        role_version=role_version,
        is_super_admin=user.is_super_admin,
        settings=settings,
    )

    user_response = UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        active_tenant_id=tenant_id,
        role=role_name,
        permissions=permissions,
        mfa_enabled=bool(user.mfa_enabled),
        is_active=bool(user.is_active),
    )

    return {
        "user": user_response,
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "csrf_token": new_csrf_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def logout_session(
    db: AsyncSession,
    redis: RedisClient,
    user_id: UUID,
    session_id: UUID,
) -> None:
    """Revoke a single active user session."""
    stmt = select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
    session_rec = (await db.execute(stmt)).scalar_one_or_none()
    if session_rec:
        session_rec.is_revoked = True
        await db.commit()

    await delete_session(redis, user_id, session_id)


async def logout_all_sessions(
    db: AsyncSession,
    redis: RedisClient,
    user_id: UUID,
) -> None:
    """Execute Global Logout across all devices adhering to Architecture Document 07 Section 6.

    Increments token_version, writes outbox row, sets force_authoritative_check = TRUE,
    and atomically evicts all user sessions from Redis via Lua.
    """
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        return

    # 1. Advance token epoch version and raise invalidation barrier flag
    user.token_version += 1
    user.force_authoritative_check = True

    # 2. Insert transactional outbox record
    outbox_entry = AuthRevocationOutbox(
        id=generate_uuid7(),
        event_type="GLOBAL_LOGOUT",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        organization_id=None,
        new_version=user.token_version,
        payload={"reason": "user_global_logout"},
    )
    db.add(outbox_entry)
    await db.commit()

    # 3. Synchronous post-commit Redis eviction via atomic monotonic Lua script
    await delete_all_user_sessions_monotonic(redis, user.id, user.token_version)


async def switch_organization(
    db: AsyncSession,
    redis: RedisClient,
    user_id: UUID,
    session_id: UUID,
    target_tenant_id: UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Switch active tenant context adhering to Architecture Document 07 Section 7."""
    # 1. Verify organization exists and is active
    org_stmt = select(Organization).where(Organization.id == target_tenant_id)
    org = (await db.execute(org_stmt)).scalar_one_or_none()
    if not org or org.status != "active":
        raise AuthorizationException(
            "Target organization does not exist or is suspended",
            error_code="ORGANIZATION_UNAVAILABLE",
        )

    # 2. Verify active membership in target organization
    mem_stmt = (
        select(OrganizationMembership)
        .options(selectinload(OrganizationMembership.role))
        .where(
            OrganizationMembership.tenant_id == target_tenant_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
    )
    membership = (await db.execute(mem_stmt)).scalar_one_or_none()
    if not membership:
        raise AuthorizationException(
            "You do not possess an active membership in the target organization",
            error_code="MEMBERSHIP_REQUIRED",
        )

    # 3. Load user and role permissions
    user_stmt = select(User).where(User.id == user_id)
    user = (await db.execute(user_stmt)).scalar_one()

    permissions = await resolve_user_permissions(db, membership.role_id)

    # 4. Update UserSession record
    sess_stmt = select(UserSession).where(
        UserSession.id == session_id, UserSession.user_id == user_id
    )
    db_session = (await db.execute(sess_stmt)).scalar_one_or_none()
    if db_session:
        db_session.tenant_id = target_tenant_id
        await db.commit()

    # 5. Update Redis session metadata
    now = utc_now()
    session_data = {
        "session_id": str(session_id),
        "user_id": str(user.id),
        "tenant_id": str(target_tenant_id),
        "role": membership.role.name,
        "token_version": user.token_version,
        "role_version": membership.role_version,
        "user_status": user.is_active,
        "membership_active": True,
        "last_db_verified_at": now.timestamp(),
        "created_at": db_session.created_at.timestamp() if db_session else now.timestamp(),
    }
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await store_session(redis, user.id, session_id, session_data, ttl_seconds=ttl_seconds)

    # 6. Issue fresh access token and CSRF token
    access_token = create_access_token(
        user_id=user.id,
        session_id=session_id,
        tenant_id=target_tenant_id,
        role=membership.role.name,
        permissions=permissions,
        token_version=user.token_version,
        role_version=membership.role_version,
        is_super_admin=user.is_super_admin,
        settings=settings,
    )
    csrf_token = generate_csrf_token()

    user_response = UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        active_tenant_id=target_tenant_id,
        role=membership.role.name,
        permissions=permissions,
        mfa_enabled=bool(user.mfa_enabled),
        is_active=bool(user.is_active),
    )

    return {
        "user": user_response,
        "access_token": access_token,
        "csrf_token": csrf_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def enroll_mfa(
    db: AsyncSession,
    user_id: UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Generate TOTP secret, backup codes, and return enrollment payload."""
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("User not found")

    secret_base32 = generate_totp_secret()
    backup_codes = generate_backup_codes(count=8)
    hashed_backup_codes = [hash_backup_code(c) for c in backup_codes]

    # Encrypt secret with AES-256-GCM before saving to PostgreSQL
    encrypted_secret = encrypt_mfa_secret(secret_base32, settings.JWT_SECRET_KEY)
    user.mfa_secret = encrypted_secret
    user.mfa_backup_codes = hashed_backup_codes
    user.mfa_enabled = False  # Not enabled until verified
    await db.commit()

    otpauth_uri = get_totp_uri(secret_base32, user.email)
    return {
        "secret": secret_base32,
        "otpauth_uri": otpauth_uri,
        "backup_codes": backup_codes,
    }


async def verify_mfa_enrollment(
    db: AsyncSession,
    user_id: UUID,
    code: str,
    settings: Settings,
) -> bool:
    """Verify code and formally activate MFA for account."""
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not user.mfa_secret:
        raise ValidationException("MFA enrollment has not been initiated")

    totp_secret = decrypt_mfa_secret(user.mfa_secret, settings.JWT_SECRET_KEY)
    if not verify_totp(totp_secret, code):
        raise AuthenticationException(
            "Invalid TOTP verification code", error_code="MFA_INVALID_CODE"
        )

    user.mfa_enabled = True
    await db.commit()
    return True


async def disable_mfa(
    db: AsyncSession,
    user_id: UUID,
    password: str,
    code: str,
    settings: Settings,
) -> bool:
    """Disable MFA after verifying current password and code."""
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("User not found")

    if not verify_password(password, user.password_hash, settings=settings):
        raise AuthenticationException("Invalid password", error_code="INVALID_CREDENTIALS")

    if user.mfa_secret:
        totp_secret = decrypt_mfa_secret(user.mfa_secret, settings.JWT_SECRET_KEY)
        if not verify_totp(totp_secret, code):
            # Check backup code
            clean = code.strip().replace("-", "").upper()
            idx = verify_backup_code(clean, user.mfa_backup_codes or [])
            if idx < 0:
                raise AuthenticationException(
                    "Invalid verification code", error_code="MFA_INVALID_CODE"
                )

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    await db.commit()
    return True


async def change_password(
    db: AsyncSession,
    redis: RedisClient,
    user_id: UUID,
    current_password: str,
    new_password: str,
    settings: Settings,
) -> None:
    """Change password, advance token version, and trigger session invalidation."""
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("User not found")

    if not verify_password(current_password, user.password_hash, settings=settings):
        raise AuthenticationException(
            "Incorrect current password", error_code="INVALID_CREDENTIALS"
        )

    user.password_hash = hash_password(new_password, settings=settings)
    user.token_version += 1
    user.force_authoritative_check = True

    outbox_entry = AuthRevocationOutbox(
        id=generate_uuid7(),
        event_type="PASSWORD_CHANGED",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        organization_id=None,
        new_version=user.token_version,
        payload={"reason": "password_change"},
    )
    db.add(outbox_entry)
    await db.commit()

    # Monotonic Redis session purge
    await delete_all_user_sessions_monotonic(redis, user.id, user.token_version)
