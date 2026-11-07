"""Test suite for application configuration and production safety validation."""

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
            POSTGRES_PASSWORD="secure_production_password_xyz",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="Insecure default POSTGRES_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="local_development_password_only",
            COOKIE_SECURE=True,
        )

    with pytest.raises(ValueError, match="COOKIE_SECURE must be True"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a_very_secure_production_jwt_signing_key_here_32_chars!",
            POSTGRES_PASSWORD="secure_production_password_xyz",
            COOKIE_SECURE=False,
        )


def test_production_settings_accept_valid_credentials() -> None:
    """Verify that production environment initializes when provided valid credentials."""
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="production_ultra_secure_jwt_signing_key_32_bytes_long!",
        POSTGRES_PASSWORD="production_db_password_strong_123!",
        COOKIE_SECURE=True,
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.COOKIE_SECURE is True
