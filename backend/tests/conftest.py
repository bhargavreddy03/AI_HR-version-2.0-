"""Global pytest fixtures and test client configuration."""

import os
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

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
        POSTGRES_PASSWORD="test_database_password_only",
        REDIS_URL="redis://localhost:6379/15",
    )


@pytest.fixture(scope="session")
def app(test_settings: Settings) -> FastAPI:
    """Instantiate application with explicit test settings."""
    return create_application(settings=test_settings)


@pytest.fixture(scope="session")
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """Provide a synchronous TestClient for API integration tests."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an asynchronous HTTPX test client."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provide an AsyncMock representation of an SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session
