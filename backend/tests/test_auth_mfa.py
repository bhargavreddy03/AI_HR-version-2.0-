"""Test suite for MFA enrollment, RFC 6238 TOTP verification, backup codes, and replay prevention."""

import json
from datetime import UTC, datetime
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
from app.modules.auth.crypto import (
    encrypt_mfa_secret,
    generate_backup_codes,
    generate_totp,
    generate_totp_secret,
    hash_backup_code,
)
from app.modules.auth.dependencies import get_app_redis
from app.modules.auth.jwt import COOKIE_ACCESS, COOKIE_CSRF, create_access_token
from app.modules.auth.models import User
from tests.test_auth_api import FakeRedis


@pytest.fixture
def mfa_client() -> tuple[TestClient, AsyncMock, FakeRedis, Settings]:
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


def test_mfa_enrollment_and_verification_flow(
    mfa_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify complete MFA enrollment: secret generation, encrypted storage, and activation with TOTP."""
    client, mock_db, fake_redis, settings = mfa_client

    user_id = uuid4()
    session_id = uuid4()
    user = User(
        id=user_id,
        email="mfa_user@example.com",
        password_hash="hash",
        first_name="MFA",
        last_name="Tester",
        is_active=True,
        mfa_enabled=False,
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user
    mock_res.scalar_one.return_value = user
    mock_db.execute.return_value = mock_res

    # Establish authenticated session
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
    client.cookies.set(COOKIE_CSRF, "csrf_secret")

    # Seed Redis session
    fake_redis.store[f"session:{user_id}:{session_id}"] = (
        f'{{"token_version": 1, "role_version": 1, "last_db_verified_at": {datetime.now(UTC).timestamp()}}}'
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "1"

    # 1. Initiate Enrollment
    res_enroll = client.post(
        "/api/v1/auth/mfa/enroll",
        headers={"X-CSRF-Token": "csrf_secret"},
    )
    assert res_enroll.status_code == status.HTTP_200_OK
    enroll_data = res_enroll.json()
    assert "secret" in enroll_data
    assert "otpauth_uri" in enroll_data
    assert len(enroll_data["backup_codes"]) == 10

    # The user record now has encrypted mfa_secret
    assert user.mfa_secret is not None
    secret = enroll_data["secret"]

    # 2. Verify with valid TOTP code to activate
    valid_code = generate_totp(secret)
    res_verify = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": valid_code},
        headers={"X-CSRF-Token": "csrf_secret"},
    )
    assert res_verify.status_code == status.HTTP_200_OK
    assert user.mfa_enabled is True


def test_mfa_login_challenge_and_verification(
    mfa_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that logging into an MFA-enabled account requires 2FA challenge completion."""
    client, mock_db, fake_redis, settings = mfa_client

    user_id = uuid4()
    totp_secret = generate_totp_secret()
    encrypted_secret = encrypt_mfa_secret(totp_secret, settings.MFA_ENCRYPTION_KEY)
    backup_codes = generate_backup_codes(4)
    hashed_backups = [
        hash_backup_code(b, secret_key=settings.BACKUP_CODE_PEPPER, user_id=user_id)
        for b in backup_codes
    ]

    raw_password = "SecurePassword123!"
    user = User(
        id=user_id,
        email="mfa_enforced@example.com",
        password_hash=hash_password(raw_password, settings=settings),
        first_name="MFA",
        last_name="Enforced",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
        mfa_backup_codes=hashed_backups,
        token_version=1,
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user
    # Mock membership queries
    mock_mem_res = MagicMock()
    mock_mem_res.scalars.return_value.first.return_value = None
    mock_db.execute.side_effect = [mock_res, mock_res, mock_mem_res]

    # Step 1: Login with password -> returns MFA challenge token
    res_login = client.post(
        "/api/v1/auth/login",
        json={"email": "mfa_enforced@example.com", "password": raw_password},
    )
    assert res_login.status_code == status.HTTP_200_OK
    login_data = res_login.json()
    assert login_data["mfa_required"] is True
    assert login_data["mfa_token"] is not None

    mfa_challenge_token = login_data["mfa_token"]

    # Step 2: Verify challenge with valid TOTP code
    totp_code = generate_totp(totp_secret)
    res_verify = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_challenge_token, "code": totp_code},
    )
    assert res_verify.status_code == status.HTTP_200_OK
    assert COOKIE_ACCESS in res_verify.cookies


def test_mfa_replay_protection(
    mfa_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that replaying the exact same TOTP code within 90s is rejected."""
    client, mock_db, fake_redis, settings = mfa_client

    user_id = uuid4()
    totp_secret = generate_totp_secret()
    encrypted_secret = encrypt_mfa_secret(totp_secret, settings.MFA_ENCRYPTION_KEY)

    user = User(
        id=user_id,
        email="replay@example.com",
        password_hash="hash",
        first_name="Replay",
        last_name="Tester",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
        token_version=1,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user
    mock_res.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_res

    challenge_token = "challenge_token_replay_test"
    fake_redis.store[f"mfa_challenge:{challenge_token}"] = json.dumps(
        {
            "user_id": str(user_id),
            "organization_slug": None,
            "token_version": 1,
        }
    )

    totp_code = generate_totp(totp_secret)

    # First attempt: succeeds
    res1 = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge_token, "code": totp_code},
    )
    assert res1.status_code == status.HTTP_200_OK

    # Replay attempt: Re-inject challenge to isolate code replay
    fake_redis.store[f"mfa_challenge:{challenge_token}"] = json.dumps(
        {
            "user_id": str(user_id),
            "organization_slug": None,
            "token_version": 1,
        }
    )

    res2 = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge_token, "code": totp_code},
    )
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED
    assert res2.json()["code"] == "MFA_CODE_REPLAYED"


def test_backup_code_single_use_and_disable_reuse(
    mfa_client: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify backup codes are single-use during login verification and cannot be reused in disable-MFA."""
    client, mock_db, fake_redis, settings = mfa_client

    user_id = uuid4()
    totp_secret = generate_totp_secret()
    encrypted_secret = encrypt_mfa_secret(totp_secret, settings.MFA_ENCRYPTION_KEY)
    backup_codes = generate_backup_codes(10)
    assert len(backup_codes) == 10
    hashed_backups = [
        hash_backup_code(b, secret_key=settings.BACKUP_CODE_PEPPER, user_id=user_id)
        for b in backup_codes
    ]

    user = User(
        id=user_id,
        email="backup@example.com",
        password_hash=hash_password("Password123!", settings=settings),
        first_name="Backup",
        last_name="Tester",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
        mfa_backup_codes=hashed_backups,
        token_version=1,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user
    mock_res.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_res

    # 1. First redemption during login challenge: succeeds and consumes code
    code_to_use = backup_codes[0]
    challenge_token_1 = "challenge_token_backup_test_1"
    fake_redis.store[f"mfa_challenge:{challenge_token_1}"] = json.dumps(
        {"user_id": str(user_id), "organization_slug": None, "token_version": 1}
    )

    res1 = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge_token_1, "code": code_to_use},
    )
    assert res1.status_code == status.HTTP_200_OK
    # Code 0 should be consumed; user now has 9 backup codes
    assert len(user.mfa_backup_codes) == 9

    # 2. Repeated redemption attempt with the same code: fails
    challenge_token_2 = "challenge_token_backup_test_2"
    fake_redis.store[f"mfa_challenge:{challenge_token_2}"] = json.dumps(
        {"user_id": str(user_id), "organization_slug": None, "token_version": 1}
    )

    res2 = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge_token_2, "code": code_to_use},
    )
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED
    assert res2.json()["code"] == "MFA_INVALID_CODE"

    # 3. Attempting to reuse the consumed code in disable-MFA flow fails
    session_id = uuid4()
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
    client.cookies.set(COOKIE_CSRF, "csrf_disable")
    fake_redis.store[f"session:{user_id}:{session_id}"] = json.dumps(
        {
            "token_version": 1,
            "role_version": 1,
            "last_db_verified_at": datetime.now(UTC).timestamp(),
        }
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "1"

    res_disable_reuse = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "Password123!", "code": code_to_use},
        headers={"X-CSRF-Token": "csrf_disable"},
    )
    assert res_disable_reuse.status_code == status.HTTP_401_UNAUTHORIZED
    assert res_disable_reuse.json()["code"] == "MFA_INVALID_CODE"
    # MFA remains enabled because code was invalid
    assert user.mfa_enabled is True
