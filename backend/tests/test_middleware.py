"""Test suite for request correlation ID tracking middleware."""

import uuid

from fastapi.testclient import TestClient


def test_correlation_id_generated_when_missing(test_client: TestClient) -> None:
    """Verify that incoming requests without correlation ID receive a generated UUID."""
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200

    correlation_id = response.headers.get("X-Correlation-ID")
    assert correlation_id is not None
    # Validate UUID format
    parsed = uuid.UUID(correlation_id)
    assert parsed.version == 4


def test_correlation_id_preserved_from_client_header(test_client: TestClient) -> None:
    """Verify that existing X-Correlation-ID header is propagated back in response."""
    custom_id = "test-custom-correlation-12345"
    response = test_client.get("/api/v1/health", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_id


def test_correlation_id_adopted_from_request_id_header(test_client: TestClient) -> None:
    """Verify that alternative X-Request-ID header is adopted if X-Correlation-ID is missing."""
    custom_req_id = "req-id-67890"
    response = test_client.get("/api/v1/health", headers={"X-Request-ID": custom_req_id})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_req_id
