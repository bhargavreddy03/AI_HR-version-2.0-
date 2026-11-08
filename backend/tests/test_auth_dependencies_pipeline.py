"""Unit tests for FastAPI authentication dependencies and the 6-layer request validation pipeline."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.core.base import utc_now
from app.core.config import get_settings
from app.core.errors import (
    AuthenticationException,
    CsrfException,
    ServiceUnavailableException,
)
from app.modules.auth.crypto import generate_csrf_token
from app.modules.auth.dependencies import (
    authenticate_request_pipeline,
    execute_authoritative_6_dim_check,
    execute_authoritative_session_check,
    extract_raw_token,
    validate_csrf,
)
from app.modules.auth.jwt import (
    COOKIE_ACCESS,
    COOKIE_CSRF,
    create_access_token,
)
from app.modules.auth.models import UserSession


def _make_request(
    method: str = "GET",
    path: str = "/api/v1/auth/me",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    """Helper to construct a Starlette Request with headers and cookies."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    cookie_header_parts = []
    if cookies:
        for k, v in cookies.items():
            cookie_header_parts.append(f"{k}={v}")
    if cookie_header_parts:
        raw_headers.append((b"cookie", "; ".join(cookie_header_parts).encode("latin-1")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
    }
    return Request(scope)


# ------------------------------------------------------------------------------
# Token Extraction Tests
# ------------------------------------------------------------------------------


def test_extract_raw_token_from_cookie() -> None:
    """Cookie extraction takes precedence or extracts valid token."""
    req = _make_request(cookies={COOKIE_ACCESS: "cookie-jwt-token"})
    assert extract_raw_token(req) == "cookie-jwt-token"


def test_extract_raw_token_from_bearer_header() -> None:
    """Authorization header extraction strips 'Bearer ' prefix."""
    req = _make_request(headers={"Authorization": "Bearer header-jwt-token"})
    assert extract_raw_token(req) == "header-jwt-token"


def test_extract_raw_token_missing_raises() -> None:
    """Missing token in both cookies and headers raises NOT_AUTHENTICATED."""
    req = _make_request()
    with pytest.raises(AuthenticationException) as exc_info:
        extract_raw_token(req)
    assert exc_info.value.code == "NOT_AUTHENTICATED"


# ------------------------------------------------------------------------------
# CSRF Validation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_csrf_safe_methods_pass_without_tokens() -> None:
    """Safe read-only HTTP methods do not enforce CSRF tokens."""
    for method in ("GET", "HEAD", "OPTIONS"):
        req = _make_request(method=method)
        await validate_csrf(req)  # Should not raise


@pytest.mark.asyncio
async def test_validate_csrf_mutating_valid_token_passes() -> None:
    """Matching CSRF cookie and header allow mutating request."""
    csrf_token = generate_csrf_token()
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        req = _make_request(
            method=method,
            headers={"X-CSRF-Token": csrf_token},
            cookies={COOKIE_CSRF: csrf_token},
        )
        await validate_csrf(req)  # Should not raise


@pytest.mark.asyncio
async def test_validate_csrf_mutating_mismatched_or_missing_rejected() -> None:
    """Mismatched or missing CSRF tokens on mutating requests raise CSRF_TOKEN_INVALID."""
    csrf_token = generate_csrf_token()

    # Missing header
    req_no_header = _make_request(method="POST", cookies={COOKIE_CSRF: csrf_token})
    with pytest.raises(CsrfException) as exc_1:
        await validate_csrf(req_no_header)
    assert exc_1.value.code == "CSRF_TOKEN_INVALID"

    # Mismatched tokens
    req_mismatch = _make_request(
        method="POST",
        headers={"X-CSRF-Token": csrf_token},
        cookies={COOKIE_CSRF: "wrong-csrf-token"},
    )
    with pytest.raises(CsrfException) as exc_2:
        await validate_csrf(req_mismatch)
    assert exc_2.value.code == "CSRF_TOKEN_INVALID"


# ------------------------------------------------------------------------------
# Authoritative PostgreSQL Session Checks
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_authoritative_session_check_malformed_uuid() -> None:
    """Malformed session or user identifier raises SESSION_INVALID."""
    mock_db = AsyncMock()
    with pytest.raises(AuthenticationException) as exc_info:
        await execute_authoritative_session_check(
            db=mock_db,
            session_id="invalid-uuid",
            user_id=str(uuid4()),
            token_version=1,
        )
    assert exc_info.value.code == "SESSION_INVALID"


@pytest.mark.asyncio
async def test_execute_authoritative_session_check_not_found() -> None:
    """Session not found in DB raises SESSION_INVALID."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(AuthenticationException) as exc_info:
        await execute_authoritative_session_check(
            db=mock_db,
            session_id=str(uuid4()),
            user_id=str(uuid4()),
            token_version=1,
        )
    assert exc_info.value.code == "SESSION_INVALID"


@pytest.mark.asyncio
async def test_execute_authoritative_session_check_revoked() -> None:
    """Revoked session raises SESSION_REVOKED."""
    mock_db = AsyncMock()
    session_rec = UserSession(
        id=uuid4(),
        user_id=uuid4(),
        token_version=1,
        is_revoked=True,
        expires_at=utc_now() + timedelta(hours=1),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = session_rec
    mock_db.execute.return_value = mock_result

    with pytest.raises(AuthenticationException) as exc_info:
        await execute_authoritative_session_check(
            db=mock_db,
            session_id=str(session_rec.id),
            user_id=str(session_rec.user_id),
            token_version=1,
        )
    assert exc_info.value.code == "SESSION_REVOKED"


@pytest.mark.asyncio
async def test_execute_authoritative_session_check_expired() -> None:
    """Expired session raises SESSION_EXPIRED."""
    mock_db = AsyncMock()
    session_rec = UserSession(
        id=uuid4(),
        user_id=uuid4(),
        token_version=1,
        is_revoked=False,
        expires_at=utc_now() - timedelta(minutes=5),  # in past
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = session_rec
    mock_db.execute.return_value = mock_result

    with pytest.raises(AuthenticationException) as exc_info:
        await execute_authoritative_session_check(
            db=mock_db,
            session_id=str(session_rec.id),
            user_id=str(session_rec.user_id),
            token_version=1,
        )
    assert exc_info.value.code == "SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_execute_authoritative_session_check_stale_token_version() -> None:
    """Token version mismatch raises TOKEN_VERSION_STALE."""
    mock_db = AsyncMock()
    session_rec = UserSession(
        id=uuid4(),
        user_id=uuid4(),
        token_version=2,  # DB has version 2
        is_revoked=False,
        expires_at=utc_now() + timedelta(hours=1),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = session_rec
    mock_db.execute.return_value = mock_result

    with pytest.raises(AuthenticationException) as exc_info:
        await execute_authoritative_session_check(
            db=mock_db,
            session_id=str(session_rec.id),
            user_id=str(session_rec.user_id),
            token_version=1,  # JWT has version 1
        )
    assert exc_info.value.code == "TOKEN_VERSION_STALE"


@pytest.mark.asyncio
async def test_execute_authoritative_6_dim_check_db_failure_fails_closed() -> None:
    """Database query failure raises ServiceUnavailableException with fail-closed posture."""
    mock_db = AsyncMock()
    mock_db.execute.side_effect = RuntimeError("DB connection dropped")

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await execute_authoritative_6_dim_check(
            db=mock_db,
            user_id=str(uuid4()),
            tenant_id=str(uuid4()),
        )
    assert exc_info.value.code == "AUTH_VALIDATION_UNAVAILABLE"


# ------------------------------------------------------------------------------
# Full 6-Layer Request Validation Pipeline Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_request_pipeline_state_b_cache_miss() -> None:
    """State B: Reachable Redis but session key absent immediately rejects without querying DB."""
    settings = get_settings()
    user_id = str(uuid4())
    session_id = str(uuid4())

    jwt_token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=["view_jobs"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    req = _make_request(cookies={COOKIE_ACCESS: jwt_token})

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Cache miss

    with pytest.raises(AuthenticationException) as exc_info:
        await authenticate_request_pipeline(
            request=req,
            db=mock_db,
            redis=mock_redis,
            settings=settings,
        )
    assert exc_info.value.code == "SESSION_REVOKED_OR_EXPIRED"
    # Crucial assertion: DB must NEVER be queried on reachable cache miss
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_authenticate_request_pipeline_state_a_affirmative_cache_hit() -> None:
    """State A: Affirmative Redis cache hit within 30s micro-validation window resolves context without DB query."""
    settings = get_settings()
    user_id = str(uuid4())
    session_id = str(uuid4())

    jwt_token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=["view_jobs"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    req = _make_request(cookies={COOKIE_ACCESS: jwt_token})

    mock_db = AsyncMock()
    mock_redis = AsyncMock()

    now = time.time()
    # Cache hit within last 10 seconds (< 30s micro-validation threshold)
    session_payload = (
        f'{{"user_id": "{user_id}", "session_id": "{session_id}", "token_version": 1, '
        f'"role_version": 1, "last_db_verified_at": {now - 10}}}'
    )

    async def fake_get(key: str) -> str | None:
        if f"session:{user_id}:{session_id}" in key:
            return session_payload
        if f"user_current_token_version:{user_id}" in key:
            return "1"
        return None

    mock_redis.get.side_effect = fake_get

    sec_ctx = await authenticate_request_pipeline(
        request=req,
        db=mock_db,
        redis=mock_redis,
        settings=settings,
    )
    assert str(sec_ctx.user_id) == user_id
    assert str(sec_ctx.session_id) == session_id
    assert sec_ctx.roles == ["candidate"]
    assert sec_ctx.permissions == ["view_jobs"]
    # DB was bypassed because of affirmative micro-validation window
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_authenticate_request_pipeline_state_a_token_fence_stale() -> None:
    """State A: If user's global token fence advanced, session is evicted and TOKEN_VERSION_STALE raised."""
    settings = get_settings()
    user_id = str(uuid4())
    session_id = str(uuid4())

    jwt_token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=[],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    req = _make_request(cookies={COOKIE_ACCESS: jwt_token})

    mock_db = AsyncMock()
    mock_redis = AsyncMock()

    now = time.time()
    session_payload = (
        f'{{"user_id": "{user_id}", "session_id": "{session_id}", "token_version": 1, '
        f'"role_version": 1, "last_db_verified_at": {now}}}'
    )

    async def fake_get(key: str) -> str | None:
        if f"session:{user_id}:{session_id}" in key:
            return session_payload
        if f"user_current_token_version:{user_id}" in key:
            return "2"  # Global fence advanced to 2
        return None

    mock_redis.get.side_effect = fake_get

    with pytest.raises(AuthenticationException) as exc_info:
        await authenticate_request_pipeline(
            request=req,
            db=mock_db,
            redis=mock_redis,
            settings=settings,
        )
    assert exc_info.value.code == "TOKEN_VERSION_STALE"
    mock_redis.delete.assert_called()


@pytest.mark.asyncio
async def test_authenticate_request_pipeline_state_c_redis_unavailable_db_fallback() -> None:
    """State C: Redis unreachable falls back to authoritative PostgreSQL validation and succeeds if DB confirms active."""
    settings = get_settings()
    user_id = str(uuid4())
    session_id = str(uuid4())

    jwt_token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=["view_jobs"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    req = _make_request(cookies={COOKIE_ACCESS: jwt_token})

    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis cluster unreachable")

    mock_db = AsyncMock()
    session_rec = UserSession(
        id=uuid4(),
        user_id=uuid4(),
        token_version=1,
        is_revoked=False,
        expires_at=utc_now() + timedelta(hours=1),
    )
    mock_session_res = MagicMock()
    mock_session_res.scalar_one_or_none.return_value = session_rec

    mock_6dim_row = {
        "user_id": user_id,
        "token_version": 1,
        "user_active": True,
        "force_authoritative_check": False,
    }
    mock_6dim_res = MagicMock()
    mock_6dim_res.mappings.return_value.first.return_value = mock_6dim_row

    mock_db.execute.side_effect = [mock_session_res, mock_6dim_res]

    sec_ctx = await authenticate_request_pipeline(
        request=req,
        db=mock_db,
        redis=mock_redis,
        settings=settings,
    )
    assert str(sec_ctx.user_id) == user_id
    assert sec_ctx.roles == ["candidate"]
    assert mock_db.execute.call_count == 2
