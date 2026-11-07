"""FastAPI authentication, session verification, and RBAC authorization dependencies.

Implements the strict 6-layer request validation pipeline conforming to Architecture Document 07.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import utc_now
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import (
    AuthenticationException,
    AuthorizationException,
    CsrfException,
    ServiceUnavailableException,
)
from app.core.redis import RedisClient, get_redis_client
from app.core.security import SecurityContext, TenantContext, set_tenant_context
from app.modules.auth.crypto import verify_csrf_token
from app.modules.auth.jwt import (
    COOKIE_ACCESS,
    COOKIE_CSRF,
    TokenPayload,
    decode_access_token,
)
from app.modules.auth.models import UserSession
from app.modules.auth.redis_session import (
    delete_session,
    get_org_role_version_fence,
    get_session,
    get_user_token_version_fence,
    touch_session_db_verified,
)

logger = logging.getLogger(__name__)

# Methods requiring CSRF validation
MUTATING_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Authoritative 6-Dimension Validation Query (Architecture Document 07 Section 4.A)
AUTHORITATIVE_6_DIM_SQL = text("""
SELECT
    u.id AS user_id,
    u.token_version,
    u.is_active AS user_active,
    u.force_authoritative_check,
    om.id AS membership_id,
    om.is_active AS membership_active,
    om.role_version,
    o.status AS organization_status
FROM users u
LEFT JOIN organization_memberships om
    ON om.user_id = u.id AND om.tenant_id = :tenant_id
LEFT JOIN organizations o
    ON o.id = :tenant_id
WHERE u.id = :user_id;
""")

AUTHORITATIVE_USER_ONLY_SQL = text("""
SELECT
    u.id AS user_id,
    u.token_version,
    u.is_active AS user_active,
    u.force_authoritative_check
FROM users u
WHERE u.id = :user_id;
""")


async def get_app_settings(request: Request) -> Settings:
    """Resolve Settings instance bound to application state with fallback to singleton."""
    return getattr(request.app.state, "settings", None) or get_settings()


async def get_app_redis(request: Request) -> RedisClient:
    """Resolve Redis client bound to application state with fallback."""
    client: RedisClient = getattr(request.app.state, "redis_client", None) or get_redis_client()
    return client


def extract_raw_token(request: Request) -> str:
    """Extract raw JWT from HttpOnly cookie or Authorization Bearer header."""
    cookie_token = request.cookies.get(COOKIE_ACCESS)
    if cookie_token:
        return cookie_token

    authorization = request.headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    raise AuthenticationException(
        "Authentication credentials were not provided",
        error_code="NOT_AUTHENTICATED",
    )


async def validate_csrf(request: Request) -> None:
    """Layer 6: Enforce CSRF header match against cookie on mutating requests."""
    if request.method in MUTATING_HTTP_METHODS:
        header_csrf = request.headers.get("X-CSRF-Token")
        cookie_csrf = request.cookies.get(COOKIE_CSRF)
        if not verify_csrf_token(header_csrf, cookie_csrf):
            raise CsrfException(
                "CSRF token verification failed",
                error_code="CSRF_TOKEN_INVALID",
            )


async def execute_authoritative_session_check(
    db: AsyncSession,
    session_id: str | UUID,
    user_id: str | UUID,
    token_version: int,
) -> UserSession:
    """Validate session directly against authoritative PostgreSQL state (State C fallback)."""
    try:
        sess_uuid = UUID(str(session_id))
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError) as exc:
        raise AuthenticationException(
            "Malformed session or user identifier", error_code="SESSION_INVALID"
        ) from exc

    stmt = select(UserSession).where(
        UserSession.id == sess_uuid,
        UserSession.user_id == user_uuid,
    )
    session_rec = (await db.execute(stmt)).scalar_one_or_none()

    if not session_rec:
        raise AuthenticationException("Session not found or invalid", error_code="SESSION_INVALID")

    if session_rec.is_revoked:
        raise AuthenticationException("Session has been revoked", error_code="SESSION_REVOKED")

    if session_rec.expires_at < utc_now():
        raise AuthenticationException("Session has expired", error_code="SESSION_EXPIRED")

    if session_rec.token_version != token_version:
        raise AuthenticationException("Token version stale", error_code="TOKEN_VERSION_STALE")

    return session_rec


async def execute_authoritative_6_dim_check(
    db: AsyncSession,
    user_id: str,
    tenant_id: str | None,
) -> dict[str, Any]:
    """Execute durable PostgreSQL authoritative check across all 6 security dimensions."""
    try:
        if tenant_id:
            result = await db.execute(
                AUTHORITATIVE_6_DIM_SQL,
                {"user_id": user_id, "tenant_id": tenant_id},
            )
            row = result.mappings().first()
            if not row:
                raise AuthenticationException("User record not found", error_code="USER_NOT_FOUND")
            return dict(row)
        else:
            result = await db.execute(
                AUTHORITATIVE_USER_ONLY_SQL,
                {"user_id": user_id},
            )
            row = result.mappings().first()
            if not row:
                raise AuthenticationException("User record not found", error_code="USER_NOT_FOUND")
            return dict(row)
    except (AuthenticationException, AuthorizationException):
        raise
    except Exception as exc:
        logger.error("Authoritative DB validation check timed out or failed: %s", exc)
        # Fail closed posture
        raise ServiceUnavailableException(
            "Security authoritative validation service unavailable",
            error_code="AUTH_VALIDATION_UNAVAILABLE",
        ) from exc


async def authenticate_request_pipeline(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
) -> SecurityContext:
    """Execute the strict 6-layer request validation pipeline."""
    # --------------------------------------------------------------------------
    # Layer 1: Cryptographic JWT Validation
    # --------------------------------------------------------------------------
    raw_token = extract_raw_token(request)
    jwt_claims: TokenPayload = decode_access_token(raw_token, settings)

    user_id = jwt_claims.sub
    session_id = jwt_claims.session_id
    tenant_id = jwt_claims.tenant_id

    # --------------------------------------------------------------------------
    # Layer 2: Server-Side Session & Exact Version Fence Verification
    # --------------------------------------------------------------------------
    session_data: dict[str, Any] | None = None
    redis_failed = False

    try:
        session_data = await get_session(redis, user_id, session_id)
        user_current_fence = await get_user_token_version_fence(redis, user_id)
        org_current_fence = (
            await get_org_role_version_fence(redis, tenant_id, user_id) if tenant_id else None
        )
    except Exception as exc:
        logger.warning("Redis unreachable during session lookup: %s (falling back to DB)", exc)
        redis_failed = True

    now_ts = time.time()

    if not redis_failed:
        # State B: Redis reachable, but session key absent (Revoked or Expired)
        if session_data is None:
            # STRICT ENFORCEMENT: Never query DB on reachable cache miss!
            raise AuthenticationException(
                "Session has been revoked or expired",
                error_code="SESSION_REVOKED_OR_EXPIRED",
            )

        # State A: Affirmative Cache Hit -> Verify Exact Invariants
        cached_token_version = session_data.get("token_version")
        cached_role_version = session_data.get("role_version", 1)

        # Invariant 1: jwt.token_version == session.token_version == user_current_token_version
        if (
            jwt_claims.token_version != cached_token_version
            or user_current_fence is None
            or jwt_claims.token_version != user_current_fence
        ):
            await delete_session(redis, user_id, session_id)
            raise AuthenticationException(
                "Session token epoch version mismatch or missing version fence",
                error_code="TOKEN_VERSION_STALE",
            )

        # Invariant 2: jwt.role_version == session.role_version == org_current_role_version
        if tenant_id and (
            jwt_claims.role_version != cached_role_version
            or org_current_fence is None
            or jwt_claims.role_version != org_current_fence
        ):
            await delete_session(redis, user_id, session_id)
            raise AuthenticationException(
                "Role version mismatch or missing role fence",
                error_code="ROLE_VERSION_STALE",
            )

        # Micro-Validation: Check if 30s elapsed since last DB verification
        last_db_verified_at = session_data.get("last_db_verified_at", 0)
        if now_ts - last_db_verified_at > 30:
            db_state = await execute_authoritative_6_dim_check(db, user_id, tenant_id)

            # Invalidation Barrier Check
            if db_state.get("force_authoritative_check"):
                # Barrier raised: Evict cache and enforce DB
                await delete_session(redis, user_id, session_id)

            # Dimension 1: User active status
            if not db_state.get("user_active"):
                await delete_session(redis, user_id, session_id)
                raise AuthenticationException(
                    "User account suspended", error_code="ACCOUNT_SUSPENDED"
                )

            # Dimension 2: User token version
            if db_state.get("token_version") != jwt_claims.token_version:
                await delete_session(redis, user_id, session_id)
                raise AuthenticationException(
                    "Token version stale", error_code="TOKEN_VERSION_STALE"
                )

            if tenant_id:
                # Dimension 3 & 4: Membership active status
                if not db_state.get("membership_id") or not db_state.get("membership_active"):
                    await delete_session(redis, user_id, session_id)
                    raise AuthorizationException(
                        "Organization membership inactive or removed",
                        error_code="MEMBERSHIP_DEACTIVATED",
                    )

                # Dimension 5: Role version
                if db_state.get("role_version") != jwt_claims.role_version:
                    await delete_session(redis, user_id, session_id)
                    raise AuthenticationException(
                        "Role version changed", error_code="ROLE_VERSION_MISMATCH"
                    )

                # Dimension 6: Organization status
                if db_state.get("organization_status") != "active":
                    await delete_session(redis, user_id, session_id)
                    raise AuthorizationException(
                        "Organization is suspended or inactive",
                        error_code="ORGANIZATION_SUSPENDED",
                    )

            # All passed: Touch last_db_verified_at
            await touch_session_db_verified(redis, user_id, session_id, now_ts)

    else:
        # State C: Redis Unavailable / Timeout -> Fallback to Authoritative PostgreSQL
        # 1. Authoritative UserSession verification against PostgreSQL
        await execute_authoritative_session_check(
            db=db,
            session_id=session_id,
            user_id=user_id,
            token_version=jwt_claims.token_version,
        )

        # 2. Authoritative 6-dimension user, membership, role, and organization verification
        db_state = await execute_authoritative_6_dim_check(db, user_id, tenant_id)

        if not db_state.get("user_active"):
            raise AuthenticationException("User account suspended", error_code="ACCOUNT_SUSPENDED")

        if db_state.get("token_version") != jwt_claims.token_version:
            raise AuthenticationException("Token version stale", error_code="TOKEN_VERSION_STALE")

        if tenant_id:
            if not db_state.get("membership_id") or not db_state.get("membership_active"):
                raise AuthorizationException(
                    "Organization membership inactive or removed",
                    error_code="MEMBERSHIP_DEACTIVATED",
                )
            if db_state.get("role_version") != jwt_claims.role_version:
                raise AuthenticationException(
                    "Role version changed", error_code="ROLE_VERSION_MISMATCH"
                )
            if db_state.get("organization_status") != "active":
                raise AuthorizationException(
                    "Organization is suspended or inactive",
                    error_code="ORGANIZATION_SUSPENDED",
                )

    # --------------------------------------------------------------------------
    # Layer 6: CSRF Validation on State Altering Requests
    # --------------------------------------------------------------------------
    if request.method in MUTATING_HTTP_METHODS:
        header_csrf = request.headers.get("X-CSRF-Token")
        cookie_csrf = request.cookies.get(COOKIE_CSRF)
        if not verify_csrf_token(header_csrf, cookie_csrf):
            raise CsrfException(
                "CSRF token verification failed",
                error_code="CSRF_TOKEN_INVALID",
            )

    # --------------------------------------------------------------------------
    # Bind Transaction-Local Tenant Context (PostgreSQL RLS)
    # --------------------------------------------------------------------------
    parsed_tenant_id = UUID(tenant_id) if tenant_id else None
    if parsed_tenant_id:
        await set_tenant_context(db, parsed_tenant_id)

    # Return Authoritative Security Context
    return SecurityContext(
        user_id=UUID(user_id),
        session_id=UUID(session_id),
        tenant_id=parsed_tenant_id,
        roles=[jwt_claims.role] if jwt_claims.role else [],
        permissions=jwt_claims.permissions,
        token_version=jwt_claims.token_version,
        role_version=jwt_claims.role_version,
        is_super_admin=jwt_claims.is_super_admin,
    )


async def require_authenticated_user(
    security_context: SecurityContext = Depends(authenticate_request_pipeline),
) -> SecurityContext:
    """Dependency requiring valid authenticated security context."""
    return security_context


async def require_active_tenant(
    security_context: SecurityContext = Depends(authenticate_request_pipeline),
) -> TenantContext:
    """Dependency requiring active tenant boundary context for multi-tenant endpoints."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context required for this operation",
            error_code="TENANT_CONTEXT_REQUIRED",
        )
    return TenantContext(tenant_id=security_context.tenant_id, is_active=True)


def require_permission(permission_code: str) -> Callable[..., Any]:
    """Dependency factory enforcing specific permission capability code within active tenant."""

    async def permission_dependency(
        request: Request,
        security_context: SecurityContext = Depends(authenticate_request_pipeline),
        settings: Settings = Depends(get_app_settings),
    ) -> SecurityContext:
        # Re-extract claims from raw token for permission inspection
        raw_token = extract_raw_token(request)
        jwt_claims = decode_access_token(raw_token, settings)

        if permission_code not in jwt_claims.permissions:
            raise AuthorizationException(
                f"Required permission '{permission_code}' is not granted",
                error_code="PERMISSION_DENIED",
            )
        return security_context

    return permission_dependency


def require_role(role_name: str) -> Callable[..., Any]:
    """Dependency factory enforcing a specific role within active tenant."""

    async def role_dependency(
        security_context: SecurityContext = Depends(authenticate_request_pipeline),
    ) -> SecurityContext:
        if role_name not in security_context.roles:
            raise AuthorizationException(
                f"Role '{role_name}' is required to perform this action",
                error_code="ROLE_REQUIRED",
            )
        return security_context

    return role_dependency
