"""Test suite for system health, liveness, and dependency readiness probe endpoints."""

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient


def test_liveness_probe_returns_200(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health returns 200 OK with valid metadata."""
    response = test_client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["environment"] == "testing"


def test_readiness_probe_healthy_when_all_dependencies_connected(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready returns 200 OK when DB and Redis are reachable."""
    with (
        patch("app.api.v1.health.check_database_health", return_value=True),
        patch("app.api.v1.health.check_redis_health", return_value=True),
    ):
        response = test_client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"] == "connected"
        assert data["dependencies"]["redis"] == "connected"


def test_readiness_probe_unhealthy_when_database_fails(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready returns 503 when the database probe fails."""
    with (
        patch("app.api.v1.health.check_database_health", return_value=False),
        patch("app.api.v1.health.check_redis_health", return_value=True),
    ):
        response = test_client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"] == "unavailable"
        assert data["dependencies"]["redis"] == "connected"


def test_readiness_probe_unhealthy_when_redis_fails(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready returns 503 when the Redis probe fails."""
    with (
        patch("app.api.v1.health.check_database_health", return_value=True),
        patch("app.api.v1.health.check_redis_health", return_value=False),
    ):
        response = test_client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"] == "connected"
        assert data["dependencies"]["redis"] == "unavailable"


def test_readiness_probe_unhealthy_when_all_dependencies_fail(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready returns 503 when both DB and Redis fail."""
    with (
        patch("app.api.v1.health.check_database_health", return_value=False),
        patch("app.api.v1.health.check_redis_health", return_value=False),
    ):
        response = test_client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"] == "unavailable"
        assert data["dependencies"]["redis"] == "unavailable"
