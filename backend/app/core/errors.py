"""Centralized exception hierarchy, RFC 7807 Problem Details schemas, and FastAPI exception handlers."""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 1. RFC 7807 Problem Details Error Schemas
# ------------------------------------------------------------------------------


class InvalidParam(BaseModel):
    """Parameter-level validation failure descriptor."""

    name: str = Field(..., description="Field or parameter name that failed validation")
    reason: str = Field(..., description="Explanation of validation constraint violation")


class ErrorResponse(BaseModel):
    """Canonical RFC 7807 Problem Details error envelope."""

    type: str = Field(
        default="https://api.ai-hr.com/v1/errors/GENERAL_ERROR",
        description="URI reference identifying the specific error category",
    )
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code for the response")
    detail: str = Field(..., description="Human-readable explanation specific to this occurrence")
    instance: str = Field(..., description="URI path of the request occurrence")
    code: str = Field(..., description="Machine-readable internal application error code")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC ISO-8601 timestamp when error occurred",
    )
    invalid_params: list[InvalidParam] | None = Field(
        default=None,
        description="List of invalid fields for 422 Unprocessable Entity responses",
    )


# ------------------------------------------------------------------------------
# 2. Application Exception Hierarchy
# ------------------------------------------------------------------------------


class AppException(Exception):
    """Root application exception with explicit status code and error classification."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "ERR_INTERNAL",
        detail: str | None = None,
        invalid_params: list[InvalidParam] | None = None,
        error_type: str = "https://api.ai-hr.com/v1/errors/INTERNAL_ERROR",
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = error_code or code
        self.error_code = self.code
        self.detail = detail or message
        self.invalid_params = invalid_params
        self.error_type = error_type


class EntityNotFoundException(AppException):
    """Raised when a requested resource does not exist or is hidden by RLS."""

    def __init__(self, entity_name: str, entity_id: UUID | str | None = None) -> None:
        detail = (
            f"{entity_name} with identifier '{entity_id}' was not found."
            if entity_id
            else f"{entity_name} was not found."
        )
        super().__init__(
            message=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            code="ERR_NOT_FOUND",
            detail=detail,
            error_type="https://api.ai-hr.com/v1/errors/NOT_FOUND",
        )


class ConflictException(AppException):
    """Raised when an operation conflicts with existing entity state."""

    def __init__(
        self,
        message: str,
        code: str = "ERR_CONFLICT",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/CONFLICT",
        )


class AuthenticationException(AppException):
    """Raised on missing, invalid, or expired authentication credentials."""

    def __init__(
        self,
        message: str = "Authentication credentials missing or invalid",
        code: str = "ERR_UNAUTHORIZED",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/UNAUTHORIZED",
        )


class AuthorizationException(AppException):
    """Raised when authenticated user lacks necessary role permissions."""

    def __init__(
        self,
        message: str = "Forbidden: Insufficient privileges for requested operation",
        code: str = "ERR_FORBIDDEN",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/FORBIDDEN",
        )


class TenantAccessForbiddenException(AuthorizationException):
    """Raised when user attempts cross-tenant boundary access."""

    def __init__(self, tenant_id: UUID | str) -> None:
        super().__init__(
            message=f"Access to tenant '{tenant_id}' is denied or membership is inactive.",
            code="ERR_TENANT_ACCESS_DENIED",
        )


class ValidationException(AppException):
    """Raised when domain business validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "ERR_VALIDATION",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/VALIDATION_ERROR",
        )


class RateLimitException(AppException):
    """Raised when request frequency exceeds rate limiting thresholds."""

    def __init__(
        self,
        message: str = "Too many requests",
        code: str = "ERR_RATE_LIMIT_EXCEEDED",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/RATE_LIMIT_EXCEEDED",
        )


class CsrfException(AppException):
    """Raised when Cross-Site Request Forgery validation fails."""

    def __init__(
        self,
        message: str = "CSRF verification failed",
        code: str = "ERR_CSRF_INVALID",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/CSRF_ERROR",
        )


class ServiceUnavailableException(AppException):
    """Raised when a downstream dependency (Database, Redis) is unreachable."""

    def __init__(
        self,
        service_name: str = "Dependency service",
        code: str = "ERR_SERVICE_UNAVAILABLE",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=f"{service_name} is currently unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=error_code or code,
            detail=f"{service_name} connection failed or timed out.",
            error_type="https://api.ai-hr.com/v1/errors/SERVICE_UNAVAILABLE",
        )


class PayloadTooLargeException(AppException):
    """Raised when request body size exceeds configured maximum limits."""

    def __init__(
        self,
        message: str = "Request body size exceeds maximum allowed limit",
        code: str = "ERR_PAYLOAD_TOO_LARGE",
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code=error_code or code,
            detail=message,
            error_type="https://api.ai-hr.com/v1/errors/PAYLOAD_TOO_LARGE",
        )


# ------------------------------------------------------------------------------
# 3. Global Exception Handlers
# ------------------------------------------------------------------------------


def _build_error_payload(
    error_type: str,
    title: str,
    status_code: int,
    detail: str,
    instance: str,
    code: str,
    invalid_params: list[InvalidParam] | None = None,
) -> dict[str, Any]:
    """Build a serialized RFC 7807 dictionary payload."""
    resp = ErrorResponse(
        type=error_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        code=code,
        invalid_params=invalid_params,
    )
    return resp.model_dump(mode="json")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle domain application exceptions."""
    payload = _build_error_payload(
        error_type=exc.error_type,
        title=exc.message,
        status_code=exc.status_code,
        detail=exc.detail,
        instance=request.url.path,
        code=exc.code,
        invalid_params=exc.invalid_params,
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Transform Pydantic validation errors into RFC 7807 problem details."""
    invalid_params: list[InvalidParam] = []
    for err in exc.errors():
        loc = ".".join(str(elem) for elem in err["loc"] if elem != "body")
        invalid_params.append(
            InvalidParam(name=loc or "body", reason=err.get("msg", "Invalid value"))
        )

    payload = _build_error_payload(
        error_type="https://api.ai-hr.com/v1/errors/VALIDATION_ERROR",
        title="Validation Failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="One or more fields failed schema validation rules.",
        instance=request.url.path,
        code="ERR_REQ_VALIDATION",
        invalid_params=invalid_params,
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)


async def http_exception_handler(
    request: Request, exc: HTTPException | StarletteHTTPException
) -> JSONResponse:
    """Handle standard Starlette/FastAPI HTTP exceptions."""
    payload = _build_error_payload(
        error_type=f"https://api.ai-hr.com/v1/errors/HTTP_{exc.status_code}",
        title=str(exc.detail),
        status_code=exc.status_code,
        detail=str(exc.detail),
        instance=request.url.path,
        code=f"ERR_HTTP_{exc.status_code}",
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all unhandled exception handler ensuring zero internal secret or traceback leakage."""
    logger.exception("Unhandled server exception processing %s: %s", request.url.path, exc)
    payload = _build_error_payload(
        error_type="https://api.ai-hr.com/v1/errors/INTERNAL_SERVER_ERROR",
        title="Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected internal server error occurred. Our team has been notified.",
        instance=request.url.path,
        code="ERR_INTERNAL_SERVER",
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(500, unhandled_exception_handler)
