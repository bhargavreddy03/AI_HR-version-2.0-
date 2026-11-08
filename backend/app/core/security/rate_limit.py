"""Redis-backed distributed rate limiting and brute-force protection.

Provides configurable window rate limiting for authentication, sensitive operations, and public endpoints
with fail-safe behavior conforming to Architecture Document 07 and 16.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request

from app.core.errors import RateLimitException, ServiceUnavailableException
from app.core.redis import RedisClient, get_redis_client

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract client IP address safely without trusting arbitrary forwarded headers."""
    # Only trust client.host by default; in reverse-proxy deployments, trusted proxies can be configured
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


async def check_rate_limit(
    redis: RedisClient,
    identifier: str,
    action: str = "general",
    max_requests: int = 60,
    window_seconds: int = 60,
    fail_closed: bool = True,
) -> tuple[bool, int, int]:
    """Check and record rate limit counter in Redis.

    Returns:
        tuple[is_allowed: bool, current_count: int, retry_after: int]
    """
    key = f"rate_limit:{action}:{identifier}"
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window_seconds)
            ttl = window_seconds
        else:
            ttl = await redis.ttl(key)
            if ttl < 0:
                # Key had no expire set; repair it
                await redis.expire(key, window_seconds)
                ttl = window_seconds

        is_allowed = bool(current <= max_requests)
        retry_after = ttl if not is_allowed else 0
        return is_allowed, current, retry_after
    except Exception as exc:
        logger.warning(
            "Redis rate limiter encounter error for key %s: %s (fail_closed=%s)",
            key,
            exc,
            fail_closed,
        )
        if fail_closed:
            raise ServiceUnavailableException(
                "Security verification service temporarily unavailable",
                error_code="RATE_LIMIT_UNAVAILABLE",
            ) from exc
        # Fail open for non-critical endpoints
        return True, 1, 0


def rate_limit(
    action: str,
    max_requests: int,
    window_seconds: int,
    fail_closed: bool = True,
) -> Callable[..., Any]:
    """FastAPI dependency factory enforcing rate limits on endpoints.

    Raises:
        RateLimitException: If request exceeds allowed rate.
        ServiceUnavailableException: If Redis fails and fail_closed=True.
    """

    async def dependency(
        request: Request,
        redis: RedisClient = Depends(get_redis_client),
    ) -> None:
        ip = get_client_ip(request)
        identifier = f"{ip}:{request.url.path}"
        is_allowed, current, retry_after = await check_rate_limit(
            redis=redis,
            identifier=identifier,
            action=action,
            max_requests=max_requests,
            window_seconds=window_seconds,
            fail_closed=fail_closed,
        )
        if not is_allowed:
            logger.warning(
                "Rate limit exceeded for %s on %s (count=%s, limit=%s)",
                ip,
                action,
                current,
                max_requests,
            )
            raise RateLimitException(
                f"Too many requests for '{action}'. Please wait {retry_after} seconds before trying again.",
                error_code="RATE_LIMIT_EXCEEDED",
            )

    return dependency
