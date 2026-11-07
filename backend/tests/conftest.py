"""Global pytest fixtures and test client configuration."""

from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(scope="session")
def test_client() -> Generator[TestClient, None, None]:
    """Provide a synchronous TestClient for API integration tests."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def override_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure test runs always use isolated test environment settings."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()
