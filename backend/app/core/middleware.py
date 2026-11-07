"""Request correlation ID tracking middleware and contextual log filters."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import Settings, get_settings

# Thread/Task-local context variable preserving the active request's correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Retrieve the correlation ID of the current request context."""
    return correlation_id_ctx.get() or "system"


class CorrelationIdFilter(logging.Filter):
    """Logging filter injecting the active correlation ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware tracking and propagating request correlation identifiers.

    Accepts an explicit Settings instance or resolves it dynamically from request.app.state.
    """

    def __init__(self, app: ASGIApp, settings: Settings | None = None, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = self.settings or getattr(request.app.state, "settings", None) or get_settings()

        # Extract existing correlation ID from incoming request headers or generate a new UUIDv4
        header_correlation_id = (
            request.headers.get(settings.CORRELATION_ID_HEADER)
            or request.headers.get(settings.REQUEST_ID_HEADER)
            or str(uuid.uuid4())
        )

        # Set context variable and request state
        token = correlation_id_ctx.set(header_correlation_id)
        request.state.correlation_id = header_correlation_id

        try:
            response = await call_next(request)
            # Propagate correlation ID in outgoing response headers
            response.headers[settings.CORRELATION_ID_HEADER] = header_correlation_id
            return response
        finally:
            correlation_id_ctx.reset(token)
