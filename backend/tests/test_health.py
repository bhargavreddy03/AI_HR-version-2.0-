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


def test_readiness_probe_distinguishes_step_3_1_placeholder(test_client: TestClient) -> None:
    """Verify that GET /api/v1/health/ready clearly reflects foundation stage without claiming premature ready DB/Redis."""
    response = test_client.get("/api/v1/health/ready")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "not_ready"
    assert data["stage"] == "step_3_1_foundation"
    assert data["dependencies"]["database"] == "pending_step_3_2_initialization"
    assert data["dependencies"]["redis"] == "pending_step_3_2_initialization"
