"""Integration and API unit tests for password reset, complexity, and session invalidation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_application
from app.modules.auth.models import User


@pytest.fixture
def test_settings() -> Settings:
    dev_pass = "test_redis_password_only"
    return Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        JWT_SECRET_KEY="test_jwt_secret_key_minimum_32_characters_long",
        POSTGRES_PASSWORD="test_database_password_only",
        REDIS_PASSWORD=dev_pass,
        REDIS_URL=f"redis://:{dev_pass}@localhost:6379/0",
        CELERY_BROKER_URL=f"redis://:{dev_pass}@localhost:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{dev_pass}@localhost:6379/2",
    )


def test_password_reset_flow_e2e(test_settings: Settings) -> None:
    """Verify password reset request, enumeration protection, token confirmation, and reuse defense."""
    app = create_application(settings=test_settings)

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    stored_redis_data: dict[str, str] = {}

    async def mock_redis_set(key: str, val: str, ex: int | None = None) -> bool:
        stored_redis_data[key] = val
        return True

    async def mock_redis_get(key: str) -> str | None:
        return stored_redis_data.get(key)

    async def mock_redis_delete(key: str) -> int:
        if key in stored_redis_data:
            del stored_redis_data[key]
            return 1
        return 0

    async def mock_redis_eval(*args: object, **kwargs: object) -> int:
        return 1

    async def mock_redis_incr(key: str) -> int:
        return 1

    async def mock_redis_expire(key: str, seconds: int) -> bool:
        return True

    async def mock_redis_ttl(key: str) -> int:
        return 60

    async def mock_redis_getdel(key: str) -> str | None:
        return stored_redis_data.pop(key, None)

    mock_redis.set = mock_redis_set
    mock_redis.get = mock_redis_get
    mock_redis.getdel = mock_redis_getdel
    mock_redis.delete = mock_redis_delete
    mock_redis.eval = mock_redis_eval
    mock_redis.incr = mock_redis_incr
    mock_redis.expire = mock_redis_expire
    mock_redis.ttl = mock_redis_ttl

    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="test_reset@example.com",
        password_hash=hash_password("OldPassword123!", settings=test_settings),
        first_name="Reset",
        last_name="User",
        token_version=1,
        is_active=True,
    )

    mock_query_result = MagicMock()
    mock_query_result.scalar_one_or_none.return_value = mock_user

    mock_sessions_result = MagicMock()
    mock_sessions_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(
        side_effect=[
            mock_query_result,  # 1. request_password_reset lookup
            mock_query_result,  # 2. confirm_password_reset user lock
            mock_sessions_result,  # 3. confirm_password_reset session revocation
        ]
    )
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    app.dependency_overrides = {}
    from app.core.database import get_db
    from app.modules.auth.dependencies import get_app_redis, get_app_settings

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_app_redis] = lambda: mock_redis
    app.dependency_overrides[get_app_settings] = lambda: test_settings

    client = TestClient(app)

    # 1. Request Password Reset -> Returns 200 with generic message
    req_resp = client.post(
        "/api/v1/auth/password/reset-request",
        json={"email": "test_reset@example.com"},
    )
    assert req_resp.status_code == 200
    assert "If the provided email is registered" in req_resp.json()["message"]
    reset_token = req_resp.json().get("reset_token")
    assert reset_token is not None

    # 2. Confirm Password Reset with weak password -> Rejected (422)
    weak_resp = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": reset_token, "new_password": "weak"},
    )
    assert weak_resp.status_code == 422

    # 3. Confirm Password Reset with strong password -> Success (200)
    confirm_resp = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": reset_token, "new_password": "NewStrongPassword2026#!"},
    )
    assert confirm_resp.status_code == 200
    assert "Password has been reset successfully" in confirm_resp.json()["message"]
    assert mock_user.token_version == 2

    # 4. Attempt to reuse consumed token -> Rejected (401)
    reuse_resp = client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": reset_token, "new_password": "AnotherNewPassword123#!"},
    )
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["code"] == "RESET_TOKEN_INVALID"


def test_password_reset_enumeration_safe(test_settings: Settings) -> None:
    """Verify non-existent user returns identical 200 message to prevent account enumeration."""
    app = create_application(settings=test_settings)

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    mock_query_result = MagicMock()
    mock_query_result.scalar_one_or_none.return_value = None  # User does not exist

    mock_db.execute = AsyncMock(return_value=mock_query_result)

    from app.core.database import get_db
    from app.modules.auth.dependencies import get_app_redis, get_app_settings

    app.dependency_overrides = {
        get_db: lambda: mock_db,
        get_app_redis: lambda: mock_redis,
        get_app_settings: lambda: test_settings,
    }

    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/password/reset-request",
        json={"email": "non_existent_user@example.com"},
    )
    assert resp.status_code == 200
    assert "If the provided email is registered" in resp.json()["message"]
    assert "reset_token" not in resp.json()  # No token exposed for non-existent user


@pytest.mark.asyncio
async def test_password_reset_token_concurrency_atomic_consumption(
    test_settings: Settings,
) -> None:
    """Verify that when two concurrent requests attempt to consume the same reset token simultaneously, exactly one succeeds."""
    import asyncio
    import json

    from app.core.errors import AuthenticationException
    from app.modules.auth.crypto import hash_token
    from app.modules.auth.service import confirm_password_reset

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    stored_redis_data: dict[str, str] = {}

    reset_token = "secure_concurrency_test_token_string_48_chars"
    token_hash = hash_token(reset_token)
    token_key = f"password_reset:{token_hash}"

    user_id = uuid.uuid4()
    token_payload = json.dumps(
        {"user_id": str(user_id), "email": "test@example.com", "token_version": 1}
    )
    stored_redis_data[token_key] = token_payload

    # Atomic getdel simulation protected by asyncio lock
    lock = asyncio.Lock()

    async def mock_redis_getdel(key: str) -> str | None:
        async with lock:
            return stored_redis_data.pop(key, None)

    mock_redis.getdel = mock_redis_getdel

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = "test@example.com"
    mock_user.is_active = True
    mock_user.token_version = 1
    mock_user.password_hash = "old_hash"

    mock_user_query = MagicMock()
    mock_user_query.scalar_one_or_none.return_value = mock_user

    mock_session_query = MagicMock()
    mock_session_query.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_user_query, mock_session_query]

    # Two concurrent requests racing to consume the exact same token
    results = await asyncio.gather(
        confirm_password_reset(
            mock_db,
            mock_redis,
            reset_token,
            "NewStrongPassword2026#!",
            "127.0.0.1",
            test_settings,
        ),
        confirm_password_reset(
            mock_db,
            mock_redis,
            reset_token,
            "NewStrongPassword2026#!",
            "127.0.0.1",
            test_settings,
        ),
        return_exceptions=True,
    )

    successes = [r for r in results if r is True]
    failures = [r for r in results if isinstance(r, AuthenticationException)]

    assert len(successes) == 1, f"Exactly one concurrent request must succeed, got {results}"
    assert len(failures) == 1, f"Exactly one concurrent request must fail, got {results}"
    assert failures[0].error_code == "RESET_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_password_reset_token_stale_version_invalidation(
    test_settings: Settings,
) -> None:
    """Verify that consuming one password reset token invalidates all previously issued reset tokens (Finding 1)."""
    import json

    from app.core.errors import AuthenticationException
    from app.modules.auth.crypto import generate_secure_token, hash_token
    from app.modules.auth.service import confirm_password_reset

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    stored_redis_data: dict[str, str] = {}

    async def mock_redis_getdel(key: str) -> str | None:
        return stored_redis_data.pop(key, None)

    mock_redis.getdel = mock_redis_getdel

    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = "stale_test@example.com"
    mock_user.is_active = True
    mock_user.token_version = 1
    mock_user.password_hash = "old_hash"

    # User requests two reset tokens before resetting password
    raw_token_1 = generate_secure_token(48)
    token_hash_1 = hash_token(raw_token_1)
    stored_redis_data[f"password_reset:{token_hash_1}"] = json.dumps(
        {"user_id": str(user_id), "email": mock_user.email, "token_version": 1}
    )

    raw_token_2 = generate_secure_token(48)
    token_hash_2 = hash_token(raw_token_2)
    stored_redis_data[f"password_reset:{token_hash_2}"] = json.dumps(
        {"user_id": str(user_id), "email": mock_user.email, "token_version": 1}
    )

    mock_user_query = MagicMock()
    mock_user_query.scalar_one_or_none.return_value = mock_user

    mock_session_query = MagicMock()
    mock_session_query.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        mock_user_query,
        mock_session_query,
        mock_user_query,
    ]

    # 1. First reset succeeds using token 1 -> increments user.token_version to 2
    success = await confirm_password_reset(
        mock_db,
        mock_redis,
        raw_token_1,
        "FirstNewPassword2026#!",
        "127.0.0.1",
        test_settings,
    )
    assert success is True
    assert mock_user.token_version == 2

    # 2. Second reset attempt using token 2 (stale token_version=1) must be rejected
    with pytest.raises(AuthenticationException) as exc_info:
        await confirm_password_reset(
            mock_db,
            mock_redis,
            raw_token_2,
            "SecondNewPassword2026#!",
            "127.0.0.1",
            test_settings,
        )
    assert exc_info.value.error_code == "RESET_TOKEN_INVALID"
    assert "invalid or has expired" in exc_info.value.message
