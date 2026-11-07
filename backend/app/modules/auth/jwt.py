"""JWT token creation, validation, and HttpOnly cookie management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import Response
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import AuthenticationException

JWT_ISSUER = "aihr-platform"
JWT_AUDIENCE = "aihr-api"

COOKIE_ACCESS = "aihr_access"
COOKIE_REFRESH = "aihr_refresh"
COOKIE_CSRF = "aihr_csrf"


class TokenPayload(BaseModel):
    """Authoritative decoded JWT claims representing authenticated session state."""

    sub: str = Field(..., description="Authenticated user UUID string")
    session_id: str = Field(..., description="Server session UUID string")
    tenant_id: str | None = Field(
        default=None, description="Active tenant UUID string if tenant-scoped"
    )
    role: str | None = Field(default=None, description="Active role name within tenant")
    permissions: list[str] = Field(default_factory=list, description="Resolved permissions")
    token_version: int = Field(default=1, description="User global token epoch version")
    role_version: int = Field(default=1, description="Membership role epoch version")
    is_super_admin: bool = Field(default=False, description="Platform super administrator flag")
    exp: int = Field(..., description="Expiration timestamp (Unix epoch)")
    iat: int = Field(..., description="Issued-at timestamp (Unix epoch)")
    iss: str = Field(default=JWT_ISSUER, description="Token issuer")
    aud: str = Field(default=JWT_AUDIENCE, description="Token audience")


def create_access_token(
    user_id: UUID | str,
    session_id: UUID | str,
    tenant_id: UUID | str | None,
    role: str | None,
    permissions: list[str],
    token_version: int,
    role_version: int,
    is_super_admin: bool,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create short-lived signed JWT access token adhering to Architecture Document 07."""
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_time = now + delta

    claims: dict[str, Any] = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role,
        "permissions": permissions,
        "token_version": token_version,
        "role_version": role_version,
        "is_super_admin": is_super_admin,
        "iat": int(now.timestamp()),
        "exp": int(expire_time.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }

    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    """Cryptographically verify signature, claims, expiry, issuer, and audience (Layer 1)."""
    try:
        decoded = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "verify_aud": True,
                "require": ["sub", "session_id", "token_version", "role_version", "exp", "iat"],
            },
        )
        return TokenPayload(**decoded)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationException(
            "Access token has expired", error_code="TOKEN_EXPIRED"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationException("Invalid access token", error_code="TOKEN_INVALID") from exc
    except Exception as exc:
        raise AuthenticationException(
            "Malformed token claims", error_code="TOKEN_MALFORMED"
        ) from exc


def get_cookie_domain(settings: Settings) -> str | None:
    """Resolve cookie domain; returns None for localhost to support standard local development."""
    domain = settings.COOKIE_DOMAIN.strip().lower()
    if domain in ("localhost", "127.0.0.1", ""):
        return None
    return domain


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    """Set secure, HttpOnly, environment-aware authentication cookies."""
    domain = get_cookie_domain(settings)
    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    # 1. Short-lived Access Token Cookie (HttpOnly)
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        domain=domain,
        path="/",
    )

    # 2. Sliding Refresh Token Cookie (HttpOnly, restricted to /api/v1/auth)
    response.set_cookie(
        key=COOKIE_REFRESH,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        domain=domain,
        path="/api/v1/auth",
    )

    # 3. CSRF Protection Cookie (Readable by frontend to populate X-CSRF-Token header)
    response.set_cookie(
        key=COOKIE_CSRF,
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        domain=domain,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Evict all platform session and authentication cookies."""
    domain = get_cookie_domain(settings)

    response.delete_cookie(
        key=COOKIE_ACCESS,
        path="/",
        domain=domain,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
    )
    response.delete_cookie(
        key=COOKIE_REFRESH,
        path="/api/v1/auth",
        domain=domain,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
    )
    response.delete_cookie(
        key=COOKIE_CSRF,
        path="/",
        domain=domain,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
    )
