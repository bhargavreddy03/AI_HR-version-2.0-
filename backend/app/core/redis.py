"""Redis asynchronous client connection pool, lifecycle, and health verification."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from redis.asyncio import ConnectionPool, Redis

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool[Any] | None = None
_redis_client: Redis[Any] | None = None


def get_redis_pool(settings: Settings | None = None) -> ConnectionPool[Any]:
    """Return cached Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        cfg = settings or get_settings()
        _redis_pool = ConnectionPool.from_url(
            cfg.REDIS_URL,
            max_connections=20,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            decode_responses=True,
        )
    return _redis_pool


def get_redis_client(settings: Settings | None = None) -> Redis[Any]:
    """Return cached Redis asynchronous client."""
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool(settings=settings)
        _redis_client = Redis(connection_pool=pool)
    return _redis_client


async def check_redis_health(client: Redis[Any] | None = None) -> bool:
    """Perform a live Redis ping probe with timeout protection."""
    r = client or get_redis_client()
    try:
        async with asyncio.timeout(2.0):
            response = await r.ping()
            return bool(response)
    except Exception as exc:
        logger.warning("Redis health check probe failed: %s", exc)
        return False


async def close_redis_connections() -> None:
    """Cleanly close Redis connections during application shutdown."""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
