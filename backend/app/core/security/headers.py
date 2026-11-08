"""HTTP security headers, browser defense, and request body size limitation middleware.

Enforces Content Security Policy (CSP), HSTS, anti-clickjacking, and streaming request size boundaries conforming to Architecture Document 11, 16, and Section 7.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, get_settings
from app.core.errors import PayloadTooLargeException, _build_error_payload

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


class SecurityHeadersMiddleware:
    """ASGI middleware injecting enterprise browser security headers and strictly bounding incoming request body sizes."""

    def __init__(
        self,
        app: ASGIApp,
        settings: Settings | None = None,
        max_body_size: int = DEFAULT_MAX_REQUEST_BODY_SIZE,
        **kwargs: Any,
    ) -> None:
        self.app = app
        self.settings = settings
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self.settings or get_settings()
        headers = dict(scope.get("headers", []))
        path = scope.get("path", "")

        # 1. Fast check: Content-Length header upfront
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
                if content_length > self.max_body_size:
                    logger.warning(
                        "Request to %s rejected: Content-Length %d exceeds limit of %d bytes",
                        path,
                        content_length,
                        self.max_body_size,
                    )
                    await self._send_413_response(scope, send)
                    return
            except ValueError:
                pass

        # 2. Enforce body size limit on actual incoming stream chunks (Finding 2)
        bytes_received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > self.max_body_size:
                    logger.warning(
                        "Request to %s rejected: stream body exceeded limit of %d bytes (%d received)",
                        path,
                        self.max_body_size,
                        bytes_received,
                    )
                    raise PayloadTooLargeException(
                        message=f"Request body size exceeds maximum limit of {self.max_body_size // (1024 * 1024)} MB",
                    )
            return message

        async def wrapped_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))

                is_https = (
                    scope.get("scheme") == "https" or headers.get(b"x-forwarded-proto") == b"https"
                )

                # Filter out headers that we override while preserving multi-value headers like set-cookie
                headers_to_override = {
                    b"x-content-type-options",
                    b"x-frame-options",
                    b"referrer-policy",
                    b"permissions-policy",
                    b"x-xss-protection",
                    b"content-security-policy",
                }
                if settings.ENVIRONMENT == "production" or is_https:
                    headers_to_override.add(b"strict-transport-security")
                if path.startswith("/api/"):
                    headers_to_override.add(b"cache-control")
                    headers_to_override.add(b"pragma")

                filtered_headers = [
                    (k, v) for k, v in raw_headers if k.lower() not in headers_to_override
                ]

                # Append security headers
                filtered_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        (
                            b"permissions-policy",
                            b"camera=(), microphone=(), geolocation=(), payment=(), usb=(), vr=()",
                        ),
                        (b"x-xss-protection", b"0"),
                        (b"content-security-policy", DEFAULT_CSP_POLICY.encode("utf-8")),
                    ]
                )

                if settings.ENVIRONMENT == "production" or is_https:
                    filtered_headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains; preload",
                        )
                    )

                if path.startswith("/api/"):
                    filtered_headers.extend(
                        [
                            (
                                b"cache-control",
                                b"no-store, no-cache, must-revalidate, max-age=0",
                            ),
                            (b"pragma", b"no-cache"),
                        ]
                    )

                message["headers"] = filtered_headers

            await send(message)

        try:
            await self.app(scope, limited_receive, wrapped_send)
        except PayloadTooLargeException:
            if not response_started:
                await self._send_413_response(scope, send)
            else:
                raise

    async def _send_413_response(self, scope: Scope, send: Send) -> None:
        """Send standardized RFC 7807 413 Payload Too Large response directly to client."""
        path = scope.get("path", "")
        payload = _build_error_payload(
            error_type="https://api.ai-hr.com/v1/errors/PAYLOAD_TOO_LARGE",
            title="Payload Too Large",
            status_code=413,
            detail=f"Request body size exceeds maximum limit of {self.max_body_size // (1024 * 1024)} MB",
            instance=path,
            code="ERR_PAYLOAD_TOO_LARGE",
        )
        body = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (
                b"permissions-policy",
                b"camera=(), microphone=(), geolocation=(), payment=(), usb=(), vr=()",
            ),
            (b"x-xss-protection", b"0"),
            (b"content-security-policy", DEFAULT_CSP_POLICY.encode("utf-8")),
        ]
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body})
