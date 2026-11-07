"""Test suite for system health and liveness probe endpoints."""

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


def test_readiness_probe_returns_200(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready returns 200 OK."""
    response = test_client.get("/api/v1/health/ready")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ready"
