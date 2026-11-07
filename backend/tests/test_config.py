"""Test suite for application configuration and production safety validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings


def test_settings_default_development() -> None:
    """Verify default development configuration settings when environment is development."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development", "DEBUG": "false"}):
        settings = Settings()
        assert settings.ENVIRONMENT == "development"
        assert settings.DEBUG is False
        assert settings.APP_NAME == "AI HR Intelligence Platform"
        assert settings.CORRELATION_ID_HEADER == "X-Correlation-ID"
        assert settings.ARGON2_MEMORY_COST >= 65536


def test_production_settings_reject_default_secrets() -> None:
    """Verify that production environment rejects default development secrets."""
    with pytest.raises(ValueError, match="Insecure or default JWT_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="local_development_jwt_secret_key_minimum_32_characters_long_for_security",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="Insecure default POSTGRES_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="local_development_password_only",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:local_development_password_only@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:local_development_password_only@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="Insecure or default MFA_ENCRYPTION_KEY"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="local_development_mfa_encryption_key_minimum_32_characters_for_security",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY must be separate and distinct"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="COOKIE_SECURE must be True"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=False,
        )


def test_production_rejects_default_database_url_when_postgres_password_is_secure() -> None:
    """Verify that insecure default DATABASE_URL is rejected even if POSTGRES_PASSWORD is secure."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DATABASE_")}
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(
            ValueError,
            match="Insecure default or development password detected in DATABASE_URL",
        ):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
                MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
                POSTGRES_PASSWORD="secure_production_password_xyz123!",
                # DATABASE_URL not supplied: retains default with 'local_development_password_only'
                DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
                COOKIE_SECURE=True,
            )


def test_production_rejects_default_sync_url_when_async_url_is_secure() -> None:
    """Verify that insecure default DATABASE_SYNC_URL is rejected even if DATABASE_URL is secure."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DATABASE_")}
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(
            ValueError,
            match="Insecure default or development password detected in DATABASE_SYNC_URL",
        ):
            Settings(
                ENVIRONMENT="production",
                JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
                MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
                POSTGRES_PASSWORD="secure_production_password_xyz123!",
                DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
                # DATABASE_SYNC_URL not supplied: retains default with 'local_development_password_only'
                COOKIE_SECURE=True,
            )


def test_production_rejects_inconsistent_database_credentials() -> None:
    """Verify rejection when DATABASE_URL credentials conflict with POSTGRES_PASSWORD."""
    with pytest.raises(ValueError, match="DATABASE_URL password does not match POSTGRES_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_password_A_1234567890!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:different_password_B_12345!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_password_A_1234567890!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_rejects_inconsistent_sync_and_async_passwords() -> None:
    """Verify rejection when DATABASE_URL and DATABASE_SYNC_URL have conflicting passwords."""
    with pytest.raises(
        ValueError, match="DATABASE_SYNC_URL password does not match POSTGRES_PASSWORD"
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_password_A_1234567890!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_password_A_1234567890!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:different_sync_pass_98765!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_rejects_inconsistent_database_username() -> None:
    """Verify rejection when URL username does not match POSTGRES_USER."""
    with pytest.raises(ValueError, match="DATABASE_URL username does not match POSTGRES_USER"):
        Settings(
            ENVIRONMENT="production",
            POSTGRES_USER="expected_db_user",
            POSTGRES_PASSWORD="secure_password_A_1234567890!",
            DATABASE_URL="postgresql+asyncpg://wrong_user:secure_password_A_1234567890!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://expected_db_user:secure_password_A_1234567890!@localhost:5432/ai_hr_db",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            COOKIE_SECURE=True,
        )


def test_production_settings_accept_consistent_secure_credentials() -> None:
    """Verify that production environment initializes when provided valid, consistent credentials."""
    secure_pass = "production_db_password_strong_123!"
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
        MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
        POSTGRES_USER="prod_app_user",
        POSTGRES_PASSWORD=secure_pass,
        DATABASE_URL=f"postgresql+asyncpg://prod_app_user:{secure_pass}@db.prod.internal:5432/ai_hr_db",
        DATABASE_SYNC_URL=f"postgresql://prod_app_user:{secure_pass}@db.prod.internal:5432/ai_hr_db",
        COOKIE_SECURE=True,
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.COOKIE_SECURE is True
    assert settings.POSTGRES_PASSWORD == secure_pass
