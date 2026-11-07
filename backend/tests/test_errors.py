"""Test suite for centralized exception handling and RFC 7807 Problem Details responses."""

import uuid

import pytest
from fastapi import APIRouter, FastAPI, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
    ServiceUnavailableException,
    TenantAccessForbiddenException,
)
from app.main import create_application


class SampleRequest(BaseModel):
    """Sample payload for validation testing."""

    email: str = Field(..., min_length=5)
    age: int = Field(..., ge=18)


@pytest.fixture
def error_test_app(test_settings: Settings) -> FastAPI:
    """Create test FastAPI application with dedicated test routes triggering exceptions."""
    non_debug_settings = test_settings.model_copy(update={"DEBUG": False})
    app = create_application(settings=non_debug_settings)
    test_router = APIRouter(prefix="/test-errors")

    @test_router.get("/app-error")
    def trigger_app_error() -> None:
        raise AppException(
            message="Domain violation occurred",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ERR_DOMAIN_RULE",
            detail="Specific domain violation details.",
        )

    @test_router.get("/not-found")
    def trigger_not_found() -> None:
        raise EntityNotFoundException("CandidateProfile", uuid.uuid4())

    @test_router.get("/conflict")
    def trigger_conflict() -> None:
        raise ConflictException("Job application already submitted.")

    @test_router.get("/unauthorized")
    def trigger_unauthorized() -> None:
        raise AuthenticationException()

    @test_router.get("/forbidden")
    def trigger_forbidden() -> None:
        raise AuthorizationException()

    @test_router.get("/tenant-forbidden")
    def trigger_tenant_forbidden() -> None:
        raise TenantAccessForbiddenException(uuid.uuid4())

    @test_router.get("/service-unavailable")
    def trigger_service_unavailable() -> None:
        raise ServiceUnavailableException("PostgreSQL Primary")

    @test_router.post("/validation")
    def trigger_validation(payload: SampleRequest) -> dict[str, str]:
        return {"status": "ok"}

    @test_router.get("/unhandled")
    def trigger_unhandled() -> None:
        raise ZeroDivisionError("division by zero internal detail")

    app.include_router(test_router)
    return app


@pytest.fixture
def error_client(error_test_app: FastAPI) -> TestClient:
    """Test client configured to receive HTTP error responses instead of re-raising in test."""
    return TestClient(error_test_app, raise_server_exceptions=False)


def test_app_exception_returns_rfc7807(error_client: TestClient) -> None:
    """Verify that domain AppException formats correctly under RFC 7807."""
    resp = error_client.get("/test-errors/app-error")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["status"] == 400
    assert data["code"] == "ERR_DOMAIN_RULE"
    assert data["detail"] == "Specific domain violation details."
    assert "timestamp" in data
    assert data["instance"] == "/test-errors/app-error"


def test_entity_not_found_exception(error_client: TestClient) -> None:
    """Verify EntityNotFoundException returns 404."""
    resp = error_client.get("/test-errors/not-found")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    data = resp.json()
    assert data["code"] == "ERR_NOT_FOUND"
    assert "CandidateProfile" in data["detail"]


def test_conflict_exception(error_client: TestClient) -> None:
    """Verify ConflictException returns 409."""
    resp = error_client.get("/test-errors/conflict")
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["code"] == "ERR_CONFLICT"


def test_authentication_and_authorization_exceptions(error_client: TestClient) -> None:
    """Verify 401 and 403 status responses."""
    resp_401 = error_client.get("/test-errors/unauthorized")
    assert resp_401.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp_401.json()["code"] == "ERR_UNAUTHORIZED"

    resp_403 = error_client.get("/test-errors/forbidden")
    assert resp_403.status_code == status.HTTP_403_FORBIDDEN
    assert resp_403.json()["code"] == "ERR_FORBIDDEN"

    resp_tenant = error_client.get("/test-errors/tenant-forbidden")
    assert resp_tenant.status_code == status.HTTP_403_FORBIDDEN
    assert resp_tenant.json()["code"] == "ERR_TENANT_ACCESS_DENIED"


def test_service_unavailable_exception(error_client: TestClient) -> None:
    """Verify ServiceUnavailableException returns 503."""
    resp = error_client.get("/test-errors/service-unavailable")
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert resp.json()["code"] == "ERR_SERVICE_UNAVAILABLE"


def test_validation_error_transforms_to_rfc7807(error_client: TestClient) -> None:
    """Verify RequestValidationError produces 422 with invalid_params list."""
    resp = error_client.post("/test-errors/validation", json={"email": "abc", "age": 15})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    data = resp.json()
    assert data["code"] == "ERR_REQ_VALIDATION"
    assert len(data["invalid_params"]) >= 2
    param_names = [p["name"] for p in data["invalid_params"]]
    assert "email" in param_names
    assert "age" in param_names


def test_unhandled_exception_does_not_leak_internals(error_client: TestClient) -> None:
    """Verify that unexpected exceptions return 500 without leaking stack traces or sensitive strings."""
    resp = error_client.get("/test-errors/unhandled")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    data = resp.json()
    assert data["code"] == "ERR_INTERNAL_SERVER"
    assert "division by zero" not in data["detail"]
    assert "Traceback" not in data["detail"]
    assert data["title"] == "Internal Server Error"
