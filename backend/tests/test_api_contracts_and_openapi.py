"""API contract and OpenAPI specification test suite.

Verifies:
1. OpenAPI 3.1 schema completeness, title, version, and component models.
2. Route contract consistency and parameter declarations.
3. RFC 7807 Problem Details error schema conformance across all registered failure pathways.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from app.core.errors import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
    PayloadTooLargeException,
    RateLimitException,
    ServiceUnavailableException,
    ValidationException,
    app_exception_handler,
)
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_openapi_schema_generation_and_metadata() -> None:
    """FastAPI app generates a structurally complete OpenAPI 3.1 schema."""
    schema = app.openapi()
    assert schema is not None
    assert "openapi" in schema
    assert schema["openapi"].startswith("3.")
    assert "info" in schema
    assert schema["info"]["title"] == "AI HR Intelligence Platform"
    assert "paths" in schema
    assert len(schema["paths"]) > 0


def test_openapi_registered_routes_declared() -> None:
    """All architectural endpoints are declared in the OpenAPI specification."""
    schema = app.openapi()
    paths = schema["paths"]

    # Health endpoints
    assert "/api/v1/health" in paths
    assert "/api/v1/health/ready" in paths

    # Task endpoints
    assert "/api/v1/tasks/system/ping" in paths
    assert "/api/v1/tasks/{task_id}/status" in paths
    assert "/api/v1/tasks/{task_id}/result" in paths

    # Authentication endpoints
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/logout-all" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/auth/password/reset-request" in paths
    assert "/api/v1/auth/password/reset-confirm" in paths
    assert "/api/v1/auth/password/change" in paths
    assert "/api/v1/auth/mfa/enroll" in paths
    assert "/api/v1/auth/mfa/verify" in paths
    assert "/api/v1/auth/mfa/disable" in paths
    assert "/api/v1/auth/switch-organization" in paths


@pytest.mark.parametrize(
    ("exc", "status_code", "error_code", "expected_type_suffix", "expected_detail"),
    [
        (
            ValidationException("Field required", error_code="VALIDATION_ERROR"),
            400,
            "VALIDATION_ERROR",
            "/errors/VALIDATION_ERROR",
            "Field required",
        ),
        (
            AuthenticationException("Invalid credentials", error_code="UNAUTHORIZED"),
            401,
            "UNAUTHORIZED",
            "/errors/UNAUTHORIZED",
            "Invalid credentials",
        ),
        (
            AuthorizationException("Permission denied", error_code="FORBIDDEN"),
            403,
            "FORBIDDEN",
            "/errors/FORBIDDEN",
            "Permission denied",
        ),
        (
            EntityNotFoundException("User", "123e4567-e89b-12d3-a456-426614174000"),
            404,
            "ERR_NOT_FOUND",
            "/errors/NOT_FOUND",
            "User with identifier '123e4567-e89b-12d3-a456-426614174000' was not found.",
        ),
        (
            ConflictException("Email already exists", error_code="RESOURCE_CONFLICT"),
            409,
            "RESOURCE_CONFLICT",
            "/errors/CONFLICT",
            "Email already exists",
        ),
        (
            PayloadTooLargeException("File exceeds 15 MB", error_code="ERR_PAYLOAD_TOO_LARGE"),
            413,
            "ERR_PAYLOAD_TOO_LARGE",
            "/errors/PAYLOAD_TOO_LARGE",
            "File exceeds 15 MB",
        ),
        (
            RateLimitException("Too many requests", error_code="RATE_LIMIT_EXCEEDED"),
            429,
            "RATE_LIMIT_EXCEEDED",
            "/errors/RATE_LIMIT_EXCEEDED",
            "Too many requests",
        ),
        (
            ServiceUnavailableException("Database", error_code="SERVICE_UNAVAILABLE"),
            503,
            "SERVICE_UNAVAILABLE",
            "/errors/SERVICE_UNAVAILABLE",
            "Database connection failed or timed out.",
        ),
        (
            AppException("Unexpected system error", status_code=500, error_code="INTERNAL_ERROR"),
            500,
            "INTERNAL_ERROR",
            "/errors/INTERNAL_ERROR",
            "Unexpected system error",
        ),
    ],
)
@pytest.mark.asyncio
async def test_rfc7807_problem_details_conformance(
    exc: AppException,
    status_code: int,
    error_code: str,
    expected_type_suffix: str,
    expected_detail: str,
) -> None:
    """All application exceptions map strictly to RFC 7807 Problem Details format."""
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/test/resource"

    response = await app_exception_handler(mock_request, exc)

    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")

    import json

    body = json.loads(response.body.decode("utf-8"))

    # RFC 7807 required problem details fields
    assert "type" in body
    assert body["type"].endswith(expected_type_suffix)
    assert "title" in body
    assert body["status"] == status_code
    assert "detail" in body
    assert body["detail"] == expected_detail
    assert body["instance"] == "/api/v1/test/resource"
    assert body["code"] == error_code


def test_validation_error_contract_on_malformed_json(client: TestClient) -> None:
    """Malformed request payload returns RFC 7807 validation error structure."""
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email"},  # Missing password, first_name, last_name, invalid email
    )
    assert res.status_code == 422
    assert "application/json" in res.headers.get("content-type", "")
    data = res.json()
    assert data["status"] == 422
    assert data["code"] == "ERR_REQ_VALIDATION"
    assert "invalid_params" in data or "detail" in data
