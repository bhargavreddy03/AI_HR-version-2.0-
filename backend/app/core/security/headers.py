"""HTTP security headers, browser defense, and request body size limitation middleware.

Enforces Content Security Policy (CSP), HSTS, anti-clickjacking, and size boundaries conforming to Architecture Document 11, 16, and Section 7.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import Settings, get_settings
from app.core.errors import _build_error_payload

logger = logging.getLogger(__name__)

# Default maximum allowable request body size (15 MB to accommodate document uploads)
DEFAULT_MAX_REQUEST_BODY_SIZE = 15 * 1024 * 1024

# Canonical CSP Policy for modern browser defense
DEFAULT_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware injecting enterprise browser security headers and limiting request sizes."""

    def __init__(
        self,
        app: ASGIApp,
        settings: Settings | None = None,
        max_body_size: int = DEFAULT_MAX_REQUEST_BODY_SIZE,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.settings = settings
        self.max_body_size = max_body_size

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = self.settings or getattr(request.app.state, "settings", None) or get_settings()

        # 1. Enforce Request Body Size Limits via Content-Length header check
        content_length_str = request.headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > self.max_body_size:
                    logger.warning(
                        "Request to %s rejected: content-length %d exceeds limit of %d bytes",
                        request.url.path,
                        content_length,
                        self.max_body_size,
                    )
                    payload = _build_error_payload(
                        error_type="https://api.ai-hr.com/v1/errors/PAYLOAD_TOO_LARGE",
                        title="Payload Too Large",
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Request body size exceeds maximum limit of {self.max_body_size // (1024 * 1024)} MB",
                        instance=request.url.path,
                        code="ERR_PAYLOAD_TOO_LARGE",
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content=payload,
                    )
            except ValueError:
                pass

        # 2. Execute inner pipeline
        response = await call_next(request)

        # 3. Inject Browser Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), vr=()"
        )
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Content-Security-Policy"] = DEFAULT_CSP_POLICY

        # In production or when served via HTTPS, enforce Strict-Transport-Security (HSTS)
        is_https = (
            request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        )
        if settings.ENVIRONMENT == "production" or is_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # For API and authenticated routes, prevent browser caching of sensitive data
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        return response
