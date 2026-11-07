"""Global pytest fixtures and test client configuration."""

import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_application


def pytest_configure(config: pytest.Config) -> None:
    """Guarantee testing environment before test collection or execution."""
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return explicit test configuration."""
    get_settings.cache_clear()
    return Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        JWT_SECRET_KEY="test_jwt_secret_key_minimum_32_characters_for_testing_suite",
    )


@pytest.fixture(scope="session")
def app(test_settings: Settings) -> FastAPI:
    """Instantiate application with test settings."""
    return create_application(settings=test_settings)


@pytest.fixture(scope="session")
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """Provide a synchronous TestClient for API integration tests."""
    with TestClient(app) as client:
        yield client
