"""Unit tests for JWT access token encoding, decoding, verification, and cookie security attributes."""

from datetime import timedelta
from uuid import uuid4

import pytest
from starlette.responses import Response

from app.core.config import Settings
from app.core.errors import AuthenticationException
from app.modules.auth.jwt import (
    COOKIE_ACCESS,
    COOKIE_CSRF,
    COOKIE_REFRESH,
    clear_auth_cookies,
    create_access_token,
    decode_access_token,
    set_auth_cookies,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        ENVIRONMENT="testing",
        JWT_SECRET_KEY="test_jwt_secret_key_minimum_32_characters_long!",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
        REFRESH_TOKEN_EXPIRE_DAYS=7,
        COOKIE_SECURE=False,
        COOKIE_SAMESITE="lax",
        COOKIE_DOMAIN="localhost",
    )


def test_jwt_create_and_decode_success(test_settings: Settings) -> None:
    """Verify standard token generation, signature validation, and claim deserialization."""
    user_id = uuid4()
    session_id = uuid4()
    tenant_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        role="recruiter",
        permissions=["jobs:create", "candidates:view_all"],
        token_version=2,
        role_version=3,
        is_super_admin=False,
        settings=test_settings,
    )

    claims = decode_access_token(token, test_settings)
    assert claims.sub == str(user_id)
    assert claims.session_id == str(session_id)
    assert claims.tenant_id == str(tenant_id)
    assert claims.role == "recruiter"
    assert "jobs:create" in claims.permissions
    assert claims.token_version == 2
    assert claims.role_version == 3
    assert claims.is_super_admin is False
    assert claims.iss == "aihr-platform"
    assert claims.aud == "aihr-api"


def test_jwt_expired_token_rejected(test_settings: Settings) -> None:
    """Verify that expired JWT access tokens are rejected with AuthenticationException."""
    token = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=None,
        role="candidate",
        permissions=[],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=test_settings,
        expires_delta=timedelta(seconds=-10),  # expired 10s ago
    )

    with pytest.raises(AuthenticationException) as exc_info:
        decode_access_token(token, test_settings)
    assert "expired" in str(exc_info.value).lower()


def test_jwt_tampered_signature_rejected(test_settings: Settings) -> None:
    """Verify that tampered tokens or wrong secret keys are rejected."""
    token = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=None,
        role="candidate",
        permissions=[],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=test_settings,
    )

    other_settings = Settings(
        ENVIRONMENT="testing",
        JWT_SECRET_KEY="completely_different_secret_key_minimum_32_chars!",
    )

    with pytest.raises(AuthenticationException):
        decode_access_token(token, other_settings)


def test_cookie_security_attributes(test_settings: Settings) -> None:
    """Verify that auth cookies set HttpOnly, SameSite, and environment-aware attributes."""
    response = Response()
    set_auth_cookies(
        response=response,
        access_token="sample_access_token",
        refresh_token="sample_refresh_token",
        csrf_token="sample_csrf_token",
        settings=test_settings,
    )

    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 3

    cookie_map: dict[str, str] = {}
    for c in cookies:
        name = c.split("=")[0].strip()
        cookie_map[name] = c

    # 1. aihr_access must be HttpOnly
    access_cookie = cookie_map[COOKIE_ACCESS]
    assert "HttpOnly" in access_cookie
    assert "Path=/" in access_cookie

    # 2. aihr_refresh must be HttpOnly and restricted to /api/v1/auth
    refresh_cookie = cookie_map[COOKIE_REFRESH]
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/v1/auth" in refresh_cookie

    # 3. aihr_csrf must NOT be HttpOnly (frontend needs to read and echo in X-CSRF-Token)
    csrf_cookie = cookie_map[COOKIE_CSRF]
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie


def test_clear_auth_cookies(test_settings: Settings) -> None:
    """Verify cookie eviction headers."""
    response = Response()
    clear_auth_cookies(response, test_settings)

    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 3
    for c in cookies:
        assert "max-age=0" in c.lower() or "expires=" in c.lower()
