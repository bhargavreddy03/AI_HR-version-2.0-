"""FastAPI API endpoints for identity, session lifecycle, MFA, and organization switching."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_db
from app.core.errors import (
    AuthenticationException,
    EntityNotFoundException,
)
from app.core.redis import RedisClient
from app.core.security import SecurityContext
from app.modules.auth.dependencies import (
    authenticate_request_pipeline,
    get_app_redis,
    get_app_settings,
    require_authenticated_user,
)
from app.modules.auth.jwt import (
    COOKIE_REFRESH,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MfaDisableRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshResponse,
    RegisterRequest,
    SwitchOrganizationRequest,
    UserResponse,
)
from app.modules.auth.service import (
    authenticate_user,
    change_password,
    confirm_password_reset,
    disable_mfa,
    enroll_mfa,
    logout_all_sessions,
    logout_session,
    refresh_session_tokens,
    register_user,
    request_password_reset,
    switch_organization,
    verify_mfa_challenge,
    verify_mfa_enrollment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new global user identity",
)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UserResponse:
    """Register a new global user account and default candidate profile."""
    user = await register_user(db=db, request=req, settings=settings)
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        active_tenant_id=None,
        role="candidate",
        permissions=["candidate:profile:manage"],
        mfa_enabled=False,
        is_active=True,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
) -> LoginResponse:
    """Authenticate with credentials and issue HttpOnly session cookies."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    auth_result, mfa_token, user_summary = await authenticate_user(
        db=db,
        redis=redis,
        login_data=req,
        client_ip=client_ip,
        user_agent=user_agent,
        settings=settings,
    )

    if mfa_token and user_summary:
        # MFA challenge required: Do not issue full session cookies yet
        return LoginResponse(
            user=user_summary,
            expires_in=300,
            mfa_required=True,
            mfa_token=mfa_token,
        )

    assert auth_result is not None
    # Set secure HttpOnly cookies
    set_auth_cookies(
        response=response,
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        csrf_token=auth_result["csrf_token"],
        settings=settings,
    )

    return LoginResponse(
        user=auth_result["user"],
        expires_in=auth_result["expires_in"],
        mfa_required=False,
        mfa_token=None,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue fresh access token",
)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
    aihr_refresh: str | None = Cookie(default=None, alias=COOKIE_REFRESH),
) -> RefreshResponse:
    """Rotate sliding refresh token, enforce reuse detection, and issue fresh cookies."""
    if not aihr_refresh:
        raise AuthenticationException(
            "Refresh token cookie is missing",
            error_code="REFRESH_TOKEN_REQUIRED",
        )

    client_ip = request.client.host if request.client else None
    result = await refresh_session_tokens(
        db=db,
        redis=redis,
        refresh_token_str=aihr_refresh,
        client_ip=client_ip,
        settings=settings,
    )

    set_auth_cookies(
        response=response,
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        csrf_token=result["csrf_token"],
        settings=settings,
    )

    return RefreshResponse(
        user=result["user"],
        expires_in=result["expires_in"],
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke active user session",
)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> dict[str, str]:
    """Revoke the calling session in PostgreSQL and Redis, and clear authentication cookies."""
    if security_context.session_id:
        await logout_session(
            db=db,
            redis=redis,
            user_id=security_context.user_id,
            session_id=security_context.session_id,
        )
    clear_auth_cookies(response=response, settings=settings)
    return {"message": "Logged out successfully"}


@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
    summary="Revoke all active sessions across all devices",
)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> dict[str, str]:
    """Execute Global Logout, incrementing token_version and evicting all Redis sessions."""
    await logout_all_sessions(db=db, redis=redis, user_id=security_context.user_id)
    clear_auth_cookies(response=response, settings=settings)
    return {"message": "All sessions revoked successfully"}


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current authenticated identity",
)
async def get_me(
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> UserResponse:
    """Return the caller's global profile, active tenant, and active permissions."""
    stmt = select(User).where(User.id == security_context.user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("User not found")

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        active_tenant_id=security_context.tenant_id,
        role=security_context.roles[0] if security_context.roles else None,
        permissions=[],
        mfa_enabled=bool(user.mfa_enabled),
        is_active=bool(user.is_active),
    )


@router.post(
    "/switch-organization",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Switch active tenant organization context",
)
async def switch_org(
    req: SwitchOrganizationRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> LoginResponse:
    """Switch organization context adhering to Architecture Document 07 Section 7."""
    from app.modules.auth.dependencies import extract_raw_token
    from app.modules.auth.jwt import decode_access_token

    raw_token = extract_raw_token(request)
    jwt_claims = decode_access_token(raw_token, settings)
    session_id = UUID(jwt_claims.session_id)

    result = await switch_organization(
        db=db,
        redis=redis,
        user_id=security_context.user_id,
        session_id=session_id,
        target_tenant_id=req.target_tenant_id,
        settings=settings,
    )

    # Set fresh access and CSRF cookies with new tenant claims
    from app.modules.auth.jwt import COOKIE_ACCESS, COOKIE_CSRF

    domain = (
        settings.COOKIE_DOMAIN
        if settings.COOKIE_DOMAIN not in ("localhost", "127.0.0.1", "")
        else None
    )
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=result["access_token"],
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        domain=domain,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_CSRF,
        value=result["csrf_token"],
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        domain=domain,
        path="/",
    )

    return LoginResponse(
        user=result["user"],
        expires_in=result["expires_in"],
        mfa_required=False,
        mfa_token=None,
    )


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate MFA enrollment",
)
async def mfa_enroll(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> MfaEnrollResponse:
    """Generate TOTP secret, otpauth URI, and one-time backup codes."""
    res = await enroll_mfa(db=db, user_id=security_context.user_id, settings=settings)
    return MfaEnrollResponse(
        secret=res["secret"],
        otpauth_uri=res["otpauth_uri"],
        backup_codes=res["backup_codes"],
    )


@router.post(
    "/mfa/verify",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify MFA code during enrollment or login challenge",
)
async def mfa_verify(
    req: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
) -> LoginResponse:
    """Verify MFA code to activate MFA on account or complete a login challenge."""
    if req.mfa_token:
        # Resolving login challenge
        result = await verify_mfa_challenge(
            db=db,
            redis=redis,
            challenge_token=req.mfa_token,
            code=req.code,
            settings=settings,
        )
        set_auth_cookies(
            response=response,
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            csrf_token=result["csrf_token"],
            settings=settings,
        )
        return LoginResponse(
            user=result["user"],
            expires_in=result["expires_in"],
            mfa_required=False,
            mfa_token=None,
        )
    else:
        # Enrollment verification: Requires authenticated session
        sec_ctx = await authenticate_request_pipeline(
            request, db=db, redis=redis, settings=settings
        )
        await verify_mfa_enrollment(
            db=db, user_id=sec_ctx.user_id, code=req.code, settings=settings
        )
        stmt = select(User).where(User.id == sec_ctx.user_id)
        user = (await db.execute(stmt)).scalar_one()
        return LoginResponse(
            user=UserResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                active_tenant_id=sec_ctx.tenant_id,
                role=sec_ctx.roles[0] if sec_ctx.roles else None,
                permissions=[],
                mfa_enabled=True,
                is_active=user.is_active,
            ),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_200_OK,
    summary="Disable MFA for account",
)
async def mfa_disable(
    req: MfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> dict[str, str]:
    """Disable MFA after confirming password and valid TOTP or backup code."""
    await disable_mfa(
        db=db,
        user_id=security_context.user_id,
        password=req.password,
        code=req.code,
        settings=settings,
    )
    return {"message": "MFA disabled successfully"}


@router.post(
    "/password/change",
    status_code=status.HTTP_200_OK,
    summary="Change password and invalidate other active sessions",
)
async def password_change(
    req: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
    security_context: SecurityContext = Depends(require_authenticated_user),
) -> dict[str, str]:
    """Change account password, advance token_version, and evict all other sessions."""
    await change_password(
        db=db,
        redis=redis,
        user_id=security_context.user_id,
        current_password=req.current_password,
        new_password=req.new_password,
        settings=settings,
    )
    return {"message": "Password changed successfully"}


@router.post(
    "/password/reset-request",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset link (enumeration-safe)",
)
async def password_reset_request(
    req: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Initiate password recovery.

    Returns a generic message to prevent account enumeration regardless of whether
    the email address exists. In non-production testing, optionally provides the token.
    """
    client_ip = request.client.host if request.client else None
    token = await request_password_reset(
        db=db,
        redis=redis,
        email=req.email,
        client_ip=client_ip,
        settings=settings,
    )
    resp: dict[str, Any] = {
        "message": "If the provided email is registered, password reset instructions have been sent."
    }
    # In development/testing environments only, expose token to facilitate automated tests
    if settings.ENVIRONMENT != "production" and token:
        resp["reset_token"] = token
    return resp


@router.post(
    "/password/reset-confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset with single-use token",
)
async def password_reset_confirm(
    req: PasswordResetConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_app_redis),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, str]:
    """Complete password reset using a single-use token, advance token version, and invalidate all sessions."""
    client_ip = request.client.host if request.client else None
    await confirm_password_reset(
        db=db,
        redis=redis,
        token=req.token,
        new_password=req.new_password,
        client_ip=client_ip,
        settings=settings,
    )
    return {
        "message": "Password has been reset successfully. Please log in with your new password."
    }
