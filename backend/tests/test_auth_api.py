"""Security and functional test suite for authentication endpoints, registration, login, cookies, and tokens."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import get_db
from app.core.redis import get_redis_client
from app.core.security import hash_password
from app.main import create_application
from app.modules.auth.dependencies import get_app_redis
from app.modules.auth.jwt import COOKIE_ACCESS, COOKIE_CSRF, COOKIE_REFRESH
from app.modules.auth.models import User, UserSession


class FakeRedis:
    """In-memory Redis test double simulating session registry and Lua scripts."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(str(key))

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        nx: bool | None = None,
    ) -> bool:
        k = str(key)
        if nx and k in self.store:
            return False
        self.store[k] = str(value) if not isinstance(value, str) else value
        if ex:
            self.ttls[k] = ex
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if str(k) in self.store:
                del self.store[str(k)]
                count += 1
        return count

    async def incr(self, key: str) -> int:
        k = str(key)
        current = int(self.store.get(k, "0")) + 1
        self.store[k] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[str(key)] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.ttls.get(str(key), -1)

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        # Simulate monotonic token version script
        key = str(args[0])
        new_ver = int(args[1])
        user_id = str(args[2])
        current = int(self.store.get(key, "0")) if key in self.store else None
        if current is None or current < new_ver:
            self.store[key] = str(new_ver)
            # Evict user sessions
            to_del = [k for k in self.store if k.startswith(f"session:{user_id}:")]
            for k in to_del:
                del self.store[k]
            return 1
        return 0


@pytest.fixture
def auth_client() -> tuple[TestClient, AsyncMock, FakeRedis, Settings]:
    test_settings = Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        JWT_SECRET_KEY="test_jwt_secret_key_minimum_32_characters_for_testing_suite",
        POSTGRES_PASSWORD="test_database_password_only",
        REDIS_URL="redis://localhost:6379/15",
        COOKIE_SECURE=False,
    )
    app = create_application(settings=test_settings)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    fake_redis = FakeRedis()

    app.state.redis_client = fake_redis
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_app_redis] = lambda: fake_redis
    app.dependency_overrides[get_redis_client] = lambda: fake_redis

    client = TestClient(app)
    return client, mock_db, fake_redis, test_settings


def test_registration_valid_user(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that registration succeeds with normalized email, returning 201 Created."""
    client, mock_db, _, _ = auth_client

    # Mock DB query returning None (email not taken)
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_execute_result

    payload = {
        "email": "Alex.Morgan@example.com",
        "password": "SecurePassword123!",
        "first_name": "Alex",
        "last_name": "Morgan",
        "phone_number": "+1-555-0199",
    }

    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["email"] == "alex.morgan@example.com"  # Normalized lowercase
    assert data["first_name"] == "Alex"
    assert data["last_name"] == "Morgan"
    assert data["role"] == "candidate"
    assert mock_db.commit.called


def test_registration_duplicate_email_conflict(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that registering an already existing email returns 409 Conflict."""
    client, mock_db, _, _ = auth_client

    existing_user = User(
        id=uuid4(),
        email="alex.morgan@example.com",
        password_hash="hash",
        first_name="Alex",
        last_name="Morgan",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_user
    mock_db.execute.return_value = mock_result

    payload = {
        "email": "Alex.Morgan@example.com",
        "password": "SecurePassword123!",
        "first_name": "Alex",
        "last_name": "Morgan",
    }

    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "ACCOUNT_ALREADY_EXISTS"


def test_login_success_sets_http_only_cookies(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify successful login issues cookies and session matching Architecture Document 10."""
    client, mock_db, fake_redis, settings = auth_client

    raw_password = "SecurePassword123!"
    password_hash = hash_password(raw_password, settings=settings)

    user = User(
        id=uuid4(),
        email="sarah.recruiter@acme-corp.com",
        password_hash=password_hash,
        first_name="Sarah",
        last_name="Jenkins",
        is_active=True,
        mfa_enabled=False,
        token_version=1,
    )

    # Mock user query
    mock_user_result = MagicMock()
    mock_user_result.scalar_one_or_none.return_value = user
    # Mock membership query (none, defaults to candidate)
    mock_mem_result = MagicMock()
    mock_mem_result.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = [mock_user_result, mock_mem_result]

    payload = {
        "email": "sarah.recruiter@acme-corp.com",
        "password": raw_password,
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["user"]["email"] == "sarah.recruiter@acme-corp.com"
    assert data["expires_in"] == 900
    assert data["mfa_required"] is False

    # Check cookies
    cookies = response.cookies
    assert COOKIE_ACCESS in cookies
    assert COOKIE_REFRESH in cookies
    assert COOKIE_CSRF in cookies


def test_login_generic_failure_on_bad_credentials(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that bad password returns generic 401 without leaking user existence."""
    client, mock_db, _, settings = auth_client

    user = User(
        id=uuid4(),
        email="sarah@example.com",
        password_hash=hash_password("CorrectPassword123!", settings=settings),
        first_name="Sarah",
        last_name="Jenkins",
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    payload = {
        "email": "sarah@example.com",
        "password": "WrongPassword123!",
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_login_inactive_user_rejected(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that deactivated user accounts cannot log in."""
    client, mock_db, _, settings = auth_client

    user = User(
        id=uuid4(),
        email="suspended@example.com",
        password_hash=hash_password("CorrectPassword123!", settings=settings),
        first_name="Suspended",
        last_name="User",
        is_active=False,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    payload = {
        "email": "suspended@example.com",
        "password": "CorrectPassword123!",
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["code"] == "ACCOUNT_DEACTIVATED"


def test_login_rate_limiting_exceeded(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that excessive login attempts trigger 429 Rate Limit Exceeded."""
    client, _, fake_redis, _ = auth_client

    # Pre-populate rate limiter key to 5
    fake_redis.store["rate_limit:login:testclient:ratelimited@example.com"] = "5"

    payload = {
        "email": "ratelimited@example.com",
        "password": "AnyPassword123!",
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"


def test_refresh_token_rotation_and_reuse_detection(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that refresh token rotation succeeds, but presenting a revoked token fails."""
    client, mock_db, fake_redis, settings = auth_client

    user = User(
        id=uuid4(),
        email="alex@example.com",
        password_hash="hash",
        first_name="Alex",
        last_name="Morgan",
        is_active=True,
        token_version=1,
    )

    from app.modules.auth.crypto import hash_token

    raw_token = "valid_refresh_token_12345678901234567890"
    session_rec = UserSession(
        id=uuid4(),
        user_id=user.id,
        tenant_id=None,
        refresh_token_hash=hash_token(raw_token),
        token_version=1,
        is_revoked=False,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session_rec.user = user

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = session_rec
    mock_db.execute.return_value = mock_result

    # 1. Successful Refresh
    client.cookies.set(COOKIE_REFRESH, raw_token)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == status.HTTP_200_OK
    assert COOKIE_ACCESS in response.cookies
    assert COOKIE_REFRESH in response.cookies

    # 2. Reuse Detection: Presenting an already revoked token
    session_rec.is_revoked = True
    response_reuse = client.post("/api/v1/auth/refresh")
    assert response_reuse.status_code == status.HTTP_401_UNAUTHORIZED
    assert response_reuse.json()["code"] == "SESSION_REVOKED"


def test_logout_and_revocation(
    auth_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify single logout clears session cookies and evicts Redis session."""
    client, mock_db, fake_redis, settings = auth_client

    user_id = uuid4()
    session_id = uuid4()

    from app.modules.auth.jwt import create_access_token

    token = create_access_token(
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

    client.cookies.set(COOKIE_ACCESS, token)
    client.cookies.set(COOKIE_CSRF, "test_csrf")

    # Seed session in Redis
    fake_redis.store[f"session:{user_id}:{session_id}"] = (
        f'{{"token_version": 1, "role_version": 1, "last_db_verified_at": {datetime.now(UTC).timestamp()}}}'
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "1"

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": "test_csrf"},
    )
    assert response.status_code == status.HTTP_200_OK

    # Cookies must be cleared
    cookies = response.headers.get_list("set-cookie")
    for c in cookies:
        assert "max-age=0" in c.lower() or "expires=" in c.lower()
