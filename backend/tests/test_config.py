"""Test suite for application configuration and production safety validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolate_migration_env_in_config_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure migration credentials from CI runner environment do not leak into general config unit tests."""
    monkeypatch.delenv("DATABASE_MIGRATION_URL", raising=False)
    monkeypatch.delenv("POSTGRES_MIGRATION_USER", raising=False)
    monkeypatch.delenv("POSTGRES_MIGRATION_PASSWORD", raising=False)


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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="Insecure or default BACKUP_CODE_PEPPER"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            BACKUP_CODE_PEPPER="local_development_backup_code_pepper_minimum_32_chars_long",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="Insecure or default BACKUP_CODE_PEPPER"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            BACKUP_CODE_PEPPER="short_pepper",
            POSTGRES_PASSWORD="secure_production_password_xyz123!",
            DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="BACKUP_CODE_PEPPER must be separate and distinct"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            MFA_ENCRYPTION_KEY="a_very_secure_production_mfa_signing_key_here_32_chars!",
            BACKUP_CODE_PEPPER="a_very_secure_production_jwt_signing_key_here_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
                BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
                BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
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
            BACKUP_CODE_PEPPER="a_very_secure_production_backup_pepper_key_32_chars!",
            COOKIE_SECURE=True,
        )


def test_production_settings_accept_consistent_secure_credentials() -> None:
    """Verify that production environment initializes when provided valid, consistent credentials."""
    secure_pass = "production_db_password_strong_123!"
    secure_redis_pass = "production_ultra_secure_redis_password_32_chars!"
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
        MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
        BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
        POSTGRES_USER="prod_app_user",
        POSTGRES_PASSWORD=secure_pass,
        DATABASE_URL=f"postgresql+asyncpg://prod_app_user:{secure_pass}@db.prod.internal:5432/ai_hr_db",
        DATABASE_SYNC_URL=f"postgresql://prod_app_user:{secure_pass}@db.prod.internal:5432/ai_hr_db",
        REDIS_PASSWORD=secure_redis_pass,
        REDIS_URL=f"redis://:{secure_redis_pass}@db.prod.internal:6379/0",
        CELERY_BROKER_URL=f"redis://:{secure_redis_pass}@db.prod.internal:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{secure_redis_pass}@db.prod.internal:6379/2",
        COOKIE_SECURE=True,
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.COOKIE_SECURE is True
    assert settings.POSTGRES_PASSWORD == secure_pass
    assert settings.REDIS_PASSWORD == secure_redis_pass


def test_production_settings_migration_role_validation() -> None:
    """Verify that when separate migration credentials are provided in production, they are strictly validated."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    secure_mig_pass = "a_very_secure_migration_password_654321!"
    secure_redis_pass = "production_ultra_secure_redis_password_32_chars!"
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
        MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
        BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
        POSTGRES_USER="aihr_app_user",
        POSTGRES_PASSWORD=secure_pass,
        POSTGRES_MIGRATION_USER="aihr_migration_user",
        POSTGRES_MIGRATION_PASSWORD=secure_mig_pass,
        DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
        DATABASE_MIGRATION_URL=f"postgresql+asyncpg://aihr_migration_user:{secure_mig_pass}@localhost:5432/ai_hr_db",
        DATABASE_SYNC_URL=f"postgresql://aihr_migration_user:{secure_mig_pass}@localhost:5432/ai_hr_db",
        REDIS_PASSWORD=secure_redis_pass,
        REDIS_URL=f"redis://:{secure_redis_pass}@localhost:6379/0",
        CELERY_BROKER_URL=f"redis://:{secure_redis_pass}@localhost:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{secure_redis_pass}@localhost:6379/2",
        COOKIE_SECURE=True,
    )
    assert settings.POSTGRES_USER == "aihr_app_user"
    assert settings.POSTGRES_MIGRATION_USER == "aihr_migration_user"
    assert settings.DATABASE_MIGRATION_URL is not None


def test_production_settings_reject_insecure_migration_password() -> None:
    """Verify that insecure password in DATABASE_MIGRATION_URL is rejected in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="Insecure default or development password detected in DATABASE_MIGRATION_URL",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            POSTGRES_MIGRATION_USER="aihr_migration_user",
            POSTGRES_MIGRATION_PASSWORD="local_development_migration_password_only",
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_migration_user:local_development_migration_password_only@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_mismatched_migration_user() -> None:
    """Verify that mismatched username in DATABASE_MIGRATION_URL is rejected in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    secure_mig_pass = "a_very_secure_migration_password_654321!"
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL username does not match POSTGRES_MIGRATION_USER",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            POSTGRES_MIGRATION_USER="aihr_migration_user",
            POSTGRES_MIGRATION_PASSWORD=secure_mig_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_MIGRATION_URL=f"postgresql+asyncpg://wrong_mig_user:{secure_mig_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_migration_user:{secure_mig_pass}@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_mismatched_migration_password() -> None:
    """Verify that mismatched password in DATABASE_MIGRATION_URL is rejected in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    secure_mig_pass = "a_very_secure_migration_password_654321!"
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL password does not match POSTGRES_MIGRATION_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            POSTGRES_MIGRATION_USER="aihr_migration_user",
            POSTGRES_MIGRATION_PASSWORD=secure_mig_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_migration_user:different_mig_password_999!@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_migration_user:{secure_mig_pass}@localhost:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_settings_accept_url_encoded_special_characters() -> None:
    """Verify that URL-encoded passwords with special characters (@, :, /, #) match plain passwords."""
    from urllib.parse import quote_plus

    raw_pass = "P@ssw0rd:Secret/Special#2026!"
    encoded_pass = quote_plus(raw_pass)
    secure_redis_pass = "P@ssw0rd:Redis/Special#2026!"
    encoded_redis_pass = quote_plus(secure_redis_pass)
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
        MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
        BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
        POSTGRES_USER="aihr_app_user",
        POSTGRES_PASSWORD=raw_pass,
        DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{encoded_pass}@localhost:5432/ai_hr_db",
        DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{encoded_pass}@localhost:5432/ai_hr_db",
        REDIS_PASSWORD=secure_redis_pass,
        REDIS_URL=f"redis://:{encoded_redis_pass}@localhost:6379/0",
        CELERY_BROKER_URL=f"redis://:{encoded_redis_pass}@localhost:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{encoded_redis_pass}@localhost:6379/2",
        COOKIE_SECURE=True,
    )
    assert settings.POSTGRES_PASSWORD == raw_pass
    assert settings.REDIS_PASSWORD == secure_redis_pass


def test_production_settings_reject_inconsistent_database_host() -> None:
    """Verify rejection when DATABASE_MIGRATION_URL host differs from DATABASE_URL host."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL host does not match DATABASE_URL host",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            POSTGRES_MIGRATION_USER="aihr_migration_user",
            POSTGRES_MIGRATION_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@primary-db.prod.internal:5432/ai_hr_db",
            DATABASE_MIGRATION_URL=f"postgresql+asyncpg://aihr_migration_user:{secure_pass}@other-db.prod.internal:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@primary-db.prod.internal:5432/ai_hr_db",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_insecure_redis_password() -> None:
    """Verify rejection when REDIS_PASSWORD is set to a development default in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="Insecure default or missing REDIS_PASSWORD detected",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD="local_development_redis_secret_only",
            REDIS_URL="redis://:local_development_redis_secret_only@localhost:6379/0",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_missing_redis_password() -> None:
    """Verify rejection when REDIS_PASSWORD is missing/empty in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="Insecure default or missing REDIS_PASSWORD detected",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD="",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_redis_url_without_password() -> None:
    """Verify rejection when REDIS_URL has no password while REDIS_PASSWORD is configured."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="Redis authentication required: REDIS_URL must contain password matching REDIS_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD="a_very_secure_production_redis_password_123!",
            REDIS_URL="redis://localhost:6379/0",  # No password in URL
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_mismatched_redis_password() -> None:
    """Verify rejection when REDIS_URL password does not match REDIS_PASSWORD in production."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    with pytest.raises(
        ValueError,
        match="REDIS_URL password does not match REDIS_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD="a_very_secure_production_redis_password_123!",
            REDIS_URL="redis://:different_production_redis_password_456!@localhost:6379/0",
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_celery_broker_url_without_password() -> None:
    """Verify rejection when CELERY_BROKER_URL has no password while REDIS_PASSWORD is configured."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    secure_redis = "a_very_secure_production_redis_password_123!"
    with pytest.raises(
        ValueError,
        match="Redis authentication required: CELERY_BROKER_URL must contain password matching REDIS_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD=secure_redis,
            REDIS_URL=f"redis://:{secure_redis}@localhost:6379/0",
            CELERY_BROKER_URL="redis://localhost:6379/1",  # No password
            COOKIE_SECURE=True,
        )


def test_production_settings_reject_celery_result_backend_mismatched_password() -> None:
    """Verify rejection when CELERY_RESULT_BACKEND password does not match REDIS_PASSWORD."""
    secure_pass = "a_very_secure_runtime_password_123456!"
    secure_redis = "a_very_secure_production_redis_password_123!"
    with pytest.raises(
        ValueError,
        match="CELERY_RESULT_BACKEND password does not match REDIS_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
            MFA_ENCRYPTION_KEY="production_ultra_secure_mfa_encryption_key_32_bytes_long!",
            BACKUP_CODE_PEPPER="production_ultra_secure_backup_pepper_32_bytes_long!",
            POSTGRES_USER="aihr_app_user",
            POSTGRES_PASSWORD=secure_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_app_user:{secure_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD=secure_redis,
            REDIS_URL=f"redis://:{secure_redis}@localhost:6379/0",
            CELERY_BROKER_URL=f"redis://:{secure_redis}@localhost:6379/1",
            CELERY_RESULT_BACKEND="redis://:mismatched_celery_pass@localhost:6379/2",
            COOKIE_SECURE=True,
        )


def test_development_redis_authentication() -> None:
    """Verify development environment enforces Redis password consistency when configured."""
    dev_pass = "local_development_redis_secret_only"
    # Valid matching development configuration
    settings = Settings(
        ENVIRONMENT="development",
        REDIS_PASSWORD=dev_pass,
        REDIS_URL=f"redis://:{dev_pass}@localhost:6379/0",
        CELERY_BROKER_URL=f"redis://:{dev_pass}@localhost:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{dev_pass}@localhost:6379/2",
    )
    assert settings.REDIS_PASSWORD == dev_pass

    # Mismatched URL in development is rejected
    with pytest.raises(ValueError, match="REDIS_URL password does not match REDIS_PASSWORD"):
        Settings(
            ENVIRONMENT="development",
            REDIS_PASSWORD=dev_pass,
            REDIS_URL="redis://:different_dev_pass@localhost:6379/0",
        )

    # Missing password in URL when REDIS_PASSWORD configured in dev is rejected
    with pytest.raises(
        ValueError,
        match="Redis authentication required: REDIS_URL must contain password matching REDIS_PASSWORD",
    ):
        Settings(
            ENVIRONMENT="development",
            REDIS_PASSWORD=dev_pass,
            REDIS_URL="redis://localhost:6379/0",
        )
