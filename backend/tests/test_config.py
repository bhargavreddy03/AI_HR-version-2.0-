"""Test suite for application configuration and production safety validation."""

from __future__ import annotations

import os
from typing import Any
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


def _valid_prod_params(**overrides: Any) -> dict[str, Any]:
    """Helper to return a complete, valid set of production Settings parameters."""
    app_pass = "secure_production_password_xyz123!"
    mig_pass = "secure_production_migration_password_456!"
    redis_pass = "secure_production_redis_password_789!"
    params: dict[str, Any] = {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "a_very_secure_production_jwt_signing_key_here_32_chars!",
        "MFA_ENCRYPTION_KEY": "a_very_secure_production_mfa_signing_key_here_32_chars!",
        "BACKUP_CODE_PEPPER": "a_very_secure_production_backup_pepper_key_32_chars!",
        "APP_ENCRYPTION_KEY": "a_very_secure_production_app_encryption_key_32_chars!",
        "POSTGRES_USER": "aihr_app_user",
        "POSTGRES_PASSWORD": app_pass,
        "POSTGRES_MIGRATION_USER": "aihr_migration_user",
        "POSTGRES_MIGRATION_PASSWORD": mig_pass,
        "DATABASE_URL": f"postgresql+asyncpg://aihr_app_user:{app_pass}@localhost:5432/ai_hr_db",
        "DATABASE_MIGRATION_URL": f"postgresql+asyncpg://aihr_migration_user:{mig_pass}@localhost:5432/ai_hr_db",
        "DATABASE_SYNC_URL": f"postgresql://aihr_migration_user:{mig_pass}@localhost:5432/ai_hr_db",
        "REDIS_PASSWORD": redis_pass,
        "REDIS_URL": f"redis://:{redis_pass}@localhost:6379/0",
        "CELERY_BROKER_URL": f"redis://:{redis_pass}@localhost:6379/1",
        "CELERY_RESULT_BACKEND": f"redis://:{redis_pass}@localhost:6379/2",
        "COOKIE_SECURE": True,
    }
    params.update(overrides)
    return params


def test_production_settings_reject_default_secrets() -> None:
    """Verify that production environment rejects default development secrets."""
    with pytest.raises(ValueError, match="Insecure or default JWT_SECRET_KEY"):
        Settings(
            **_valid_prod_params(
                JWT_SECRET_KEY="local_development_jwt_secret_key_minimum_32_characters_long_for_security",
            )
        )

    with pytest.raises(ValueError, match="Insecure default POSTGRES_PASSWORD"):
        Settings(
            **_valid_prod_params(
                POSTGRES_PASSWORD="local_development_password_only",
                DATABASE_URL="postgresql+asyncpg://aihr_app_user:local_development_password_only@localhost:5432/ai_hr_db",
            )
        )

    with pytest.raises(ValueError, match="Insecure or default MFA_ENCRYPTION_KEY"):
        Settings(
            **_valid_prod_params(
                MFA_ENCRYPTION_KEY="local_development_mfa_encryption_key_minimum_32_characters_for_security",
            )
        )

    with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY must be separate and distinct"):
        Settings(
            **_valid_prod_params(
                MFA_ENCRYPTION_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            )
        )

    with pytest.raises(ValueError, match="Insecure or default BACKUP_CODE_PEPPER"):
        Settings(
            **_valid_prod_params(
                BACKUP_CODE_PEPPER="local_development_backup_code_pepper_minimum_32_chars_long",
            )
        )

    with pytest.raises(ValueError, match="Insecure or default BACKUP_CODE_PEPPER"):
        Settings(
            **_valid_prod_params(
                BACKUP_CODE_PEPPER="short_pepper",
            )
        )

    with pytest.raises(ValueError, match="BACKUP_CODE_PEPPER must be separate and distinct"):
        Settings(
            **_valid_prod_params(
                BACKUP_CODE_PEPPER="a_very_secure_production_jwt_signing_key_here_32_chars!",
            )
        )

    with pytest.raises(ValueError, match="COOKIE_SECURE must be True"):
        Settings(
            **_valid_prod_params(
                COOKIE_SECURE=False,
            )
        )


def test_production_rejects_default_database_url_when_postgres_password_is_secure() -> None:
    """Verify that insecure default DATABASE_URL is rejected even if POSTGRES_PASSWORD is secure."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DATABASE_")}
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(
            ValueError,
            match="Insecure default or development password detected in DATABASE_URL",
        ):
            params = _valid_prod_params()
            del params["DATABASE_URL"]
            Settings(**params)


def test_production_rejects_default_sync_url_when_async_url_is_secure() -> None:
    """Verify that insecure default DATABASE_SYNC_URL is rejected even if DATABASE_URL is secure."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DATABASE_")}
    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(
            ValueError,
            match="Insecure default or development password detected in DATABASE_SYNC_URL",
        ):
            params = _valid_prod_params()
            del params["DATABASE_SYNC_URL"]
            Settings(**params)


def test_production_rejects_inconsistent_database_credentials() -> None:
    """Verify rejection when DATABASE_URL credentials conflict with POSTGRES_PASSWORD."""
    with pytest.raises(ValueError, match="DATABASE_URL password does not match POSTGRES_PASSWORD"):
        Settings(
            **_valid_prod_params(
                DATABASE_URL="postgresql+asyncpg://aihr_app_user:different_password_B_12345!@localhost:5432/ai_hr_db",
            )
        )


def test_production_rejects_inconsistent_sync_and_async_passwords() -> None:
    """Verify rejection when DATABASE_SYNC_URL password does not match POSTGRES_MIGRATION_PASSWORD."""
    with pytest.raises(
        ValueError, match="DATABASE_SYNC_URL password does not match POSTGRES_MIGRATION_PASSWORD"
    ):
        Settings(
            **_valid_prod_params(
                DATABASE_SYNC_URL="postgresql://aihr_migration_user:different_sync_pass_98765!@localhost:5432/ai_hr_db",
            )
        )


def test_production_rejects_inconsistent_database_username() -> None:
    """Verify rejection when URL username does not match POSTGRES_USER."""
    with pytest.raises(ValueError, match="DATABASE_URL username does not match POSTGRES_USER"):
        Settings(
            **_valid_prod_params(
                DATABASE_URL="postgresql+asyncpg://wrong_user:secure_production_password_xyz123!@localhost:5432/ai_hr_db",
            )
        )


def test_production_settings_accept_consistent_secure_credentials() -> None:
    """Verify that production environment initializes when provided valid, consistent credentials."""
    params = _valid_prod_params()
    settings = Settings(**params)
    assert settings.ENVIRONMENT == "production"
    assert settings.COOKIE_SECURE is True
    assert settings.POSTGRES_USER == "aihr_app_user"
    assert settings.POSTGRES_MIGRATION_USER == "aihr_migration_user"


def test_production_settings_migration_role_validation() -> None:
    """Verify that migration credentials and URLs are strictly required and validated in production."""
    params = _valid_prod_params()
    settings = Settings(**params)
    assert settings.POSTGRES_MIGRATION_USER == "aihr_migration_user"
    assert settings.DATABASE_MIGRATION_URL is not None
    assert settings.DATABASE_SYNC_URL is not None


def test_production_settings_reject_role_collision() -> None:
    """Verify production rejects role collisions between migration user and runtime app user."""
    with pytest.raises(
        ValueError, match="POSTGRES_MIGRATION_USER cannot match runtime POSTGRES_USER"
    ):
        Settings(
            **_valid_prod_params(
                POSTGRES_MIGRATION_USER="aihr_app_user",
                DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_app_user:secure_production_migration_password_456!@localhost:5432/ai_hr_db",
                DATABASE_SYNC_URL="postgresql://aihr_app_user:secure_production_migration_password_456!@localhost:5432/ai_hr_db",
            )
        )


def test_production_settings_reject_insecure_migration_password() -> None:
    """Verify that insecure password in POSTGRES_MIGRATION_PASSWORD or DATABASE_MIGRATION_URL is rejected in production."""
    with pytest.raises(
        ValueError,
        match="Insecure default or missing POSTGRES_MIGRATION_PASSWORD detected",
    ):
        Settings(
            **_valid_prod_params(
                POSTGRES_MIGRATION_PASSWORD="local_development_migration_password_only",
            )
        )

    with pytest.raises(
        ValueError,
        match="Insecure default or development password detected in DATABASE_MIGRATION_URL",
    ):
        Settings(
            **_valid_prod_params(
                DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_migration_user:local_development_migration_password_only@localhost:5432/ai_hr_db",
            )
        )


def test_production_settings_reject_mismatched_migration_user() -> None:
    """Verify that mismatched username in DATABASE_MIGRATION_URL is rejected in production."""
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL username.*POSTGRES_MIGRATION_USER",
    ):
        Settings(
            **_valid_prod_params(
                DATABASE_MIGRATION_URL="postgresql+asyncpg://wrong_mig_user:secure_production_migration_password_456!@localhost:5432/ai_hr_db",
            )
        )


def test_production_settings_reject_mismatched_migration_password() -> None:
    """Verify that mismatched password in DATABASE_MIGRATION_URL is rejected in production."""
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL password does not match POSTGRES_MIGRATION_PASSWORD",
    ):
        Settings(
            **_valid_prod_params(
                DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_migration_user:different_mig_password_999!@localhost:5432/ai_hr_db",
            )
        )


def test_production_settings_accept_url_encoded_special_characters() -> None:
    """Verify that URL-encoded passwords with special characters (@, :, /, #) match plain passwords."""
    from urllib.parse import quote_plus

    raw_app_pass = "P@ssw0rd:Secret/Special#2026!"
    encoded_app_pass = quote_plus(raw_app_pass)
    raw_mig_pass = "M1gr@te:Secret/Special#2026!"
    encoded_mig_pass = quote_plus(raw_mig_pass)
    raw_redis_pass = "P@ssw0rd:Redis/Special#2026!"
    encoded_redis_pass = quote_plus(raw_redis_pass)

    settings = Settings(
        **_valid_prod_params(
            POSTGRES_PASSWORD=raw_app_pass,
            POSTGRES_MIGRATION_PASSWORD=raw_mig_pass,
            DATABASE_URL=f"postgresql+asyncpg://aihr_app_user:{encoded_app_pass}@localhost:5432/ai_hr_db",
            DATABASE_MIGRATION_URL=f"postgresql+asyncpg://aihr_migration_user:{encoded_mig_pass}@localhost:5432/ai_hr_db",
            DATABASE_SYNC_URL=f"postgresql://aihr_migration_user:{encoded_mig_pass}@localhost:5432/ai_hr_db",
            REDIS_PASSWORD=raw_redis_pass,
            REDIS_URL=f"redis://:{encoded_redis_pass}@localhost:6379/0",
            CELERY_BROKER_URL=f"redis://:{encoded_redis_pass}@localhost:6379/1",
            CELERY_RESULT_BACKEND=f"redis://:{encoded_redis_pass}@localhost:6379/2",
        )
    )
    assert settings.POSTGRES_PASSWORD == raw_app_pass
    assert settings.POSTGRES_MIGRATION_PASSWORD == raw_mig_pass
    assert settings.REDIS_PASSWORD == raw_redis_pass


def test_production_settings_reject_inconsistent_database_host() -> None:
    """Verify rejection when DATABASE_MIGRATION_URL host differs from DATABASE_URL host."""
    with pytest.raises(
        ValueError,
        match="DATABASE_MIGRATION_URL host does not match DATABASE_URL host",
    ):
        Settings(
            **_valid_prod_params(
                DATABASE_URL="postgresql+asyncpg://aihr_app_user:secure_production_password_xyz123!@primary-db.prod.internal:5432/ai_hr_db",
                DATABASE_MIGRATION_URL="postgresql+asyncpg://aihr_migration_user:secure_production_migration_password_456!@other-db.prod.internal:5432/ai_hr_db",
                DATABASE_SYNC_URL="postgresql://aihr_migration_user:secure_production_migration_password_456!@primary-db.prod.internal:5432/ai_hr_db",
            )
        )


def test_production_settings_reject_insecure_redis_password() -> None:
    """Verify rejection when REDIS_PASSWORD is set to a development default in production."""
    with pytest.raises(
        ValueError,
        match="Insecure default or missing REDIS_PASSWORD detected",
    ):
        Settings(
            **_valid_prod_params(
                REDIS_PASSWORD="local_development_redis_secret_only",
                REDIS_URL="redis://:local_development_redis_secret_only@localhost:6379/0",
            )
        )


def test_production_settings_reject_missing_redis_password() -> None:
    """Verify rejection when REDIS_PASSWORD is missing/empty in production."""
    with pytest.raises(
        ValueError,
        match="Insecure default or missing REDIS_PASSWORD detected",
    ):
        Settings(
            **_valid_prod_params(
                REDIS_PASSWORD="",
            )
        )


def test_production_settings_reject_redis_url_without_password() -> None:
    """Verify rejection when REDIS_URL has no password while REDIS_PASSWORD is configured."""
    with pytest.raises(
        ValueError,
        match="Redis authentication required: REDIS_URL must contain password matching REDIS_PASSWORD",
    ):
        Settings(
            **_valid_prod_params(
                REDIS_URL="redis://localhost:6379/0",
            )
        )


def test_production_settings_reject_mismatched_redis_password() -> None:
    """Verify rejection when REDIS_URL password does not match REDIS_PASSWORD in production."""
    with pytest.raises(
        ValueError,
        match="REDIS_URL password does not match REDIS_PASSWORD",
    ):
        Settings(
            **_valid_prod_params(
                REDIS_URL="redis://:different_production_redis_password_456!@localhost:6379/0",
            )
        )


def test_production_settings_reject_celery_broker_url_without_password() -> None:
    """Verify rejection when CELERY_BROKER_URL has no password while REDIS_PASSWORD is configured."""
    with pytest.raises(
        ValueError,
        match="Redis authentication required: CELERY_BROKER_URL must contain password matching REDIS_PASSWORD",
    ):
        Settings(
            **_valid_prod_params(
                CELERY_BROKER_URL="redis://localhost:6379/1",
            )
        )


def test_production_settings_reject_celery_result_backend_mismatched_password() -> None:
    """Verify rejection when CELERY_RESULT_BACKEND password does not match REDIS_PASSWORD."""
    with pytest.raises(
        ValueError,
        match="CELERY_RESULT_BACKEND password does not match REDIS_PASSWORD",
    ):
        Settings(
            **_valid_prod_params(
                CELERY_RESULT_BACKEND="redis://:mismatched_celery_pass@localhost:6379/2",
            )
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
