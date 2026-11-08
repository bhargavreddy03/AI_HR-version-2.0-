"""Redis asynchronous client connection pool, lifecycle, and health verification."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import redis
from redis.asyncio import ConnectionPool, Redis

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    RedisClient = Redis[Any]
else:
    RedisClient = Any

_redis_pool: ConnectionPool[Any] | None = None
_redis_client: Redis[Any] | None = None
_sync_redis_pool: redis.ConnectionPool | None = None
_sync_redis_client: redis.Redis[Any] | None = None


def create_redis_pool(settings: Settings) -> ConnectionPool[Any]:
    """Create a new Redis connection pool bound to settings.

    REDIS_URL serves as the single authoritative connection and authentication
    configuration, embedding the protocol scheme, authentication credentials, host,
    port, and target database index.
    """
    return ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=20,
        socket_timeout=3.0,
        socket_connect_timeout=3.0,
        decode_responses=True,
    )


def create_redis_client(settings: Settings) -> Redis[Any]:
    """Create a new Redis async client bound to settings."""
    pool = create_redis_pool(settings)
    return Redis(connection_pool=pool)


def get_redis_pool(settings: Settings | None = None) -> ConnectionPool[Any]:
    """Return cached Redis connection pool or create one for settings."""
    global _redis_pool
    cfg = settings or get_settings()
    if _redis_pool is None:
        _redis_pool = create_redis_pool(cfg)
    return _redis_pool


def get_redis_client(settings: Settings | None = None) -> Redis[Any]:
    """Return cached Redis asynchronous client or create one for settings."""
    global _redis_client
    if _redis_client is None:
        cfg = settings or get_settings()
        _redis_client = create_redis_client(cfg)
    return _redis_client


def create_sync_redis_pool(settings: Settings) -> redis.ConnectionPool:
    """Create a new synchronous Redis connection pool bound to settings.

    Uses REDIS_URL as single authoritative source of connection truth.
    """
    return redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=20,
        socket_timeout=3.0,
        socket_connect_timeout=3.0,
        decode_responses=True,
    )


def create_sync_redis_client(settings: Settings) -> redis.Redis[Any]:
    """Create a new synchronous Redis client bound to settings."""
    pool = create_sync_redis_pool(settings)
    return redis.Redis(connection_pool=pool)


def get_sync_redis_pool(settings: Settings | None = None) -> redis.ConnectionPool:
    """Return cached synchronous Redis connection pool or create one for settings."""
    global _sync_redis_pool
    cfg = settings or get_settings()
    if _sync_redis_pool is None:
        _sync_redis_pool = create_sync_redis_pool(cfg)
    return _sync_redis_pool


def get_sync_redis_client(settings: Settings | None = None) -> redis.Redis[Any]:
    """Return cached synchronous Redis client or create one for settings."""
    global _sync_redis_client
    if _sync_redis_client is None:
        cfg = settings or get_settings()
        _sync_redis_client = create_sync_redis_client(cfg)
    return _sync_redis_client


async def check_redis_health(
    client: Redis[Any] | None = None,
    settings: Settings | None = None,
) -> bool:
    """Perform a live Redis ping probe with timeout protection."""
    r = client or get_redis_client(settings=settings)
    try:
        async with asyncio.timeout(2.0):
            response = await r.ping()
            return bool(response)
    except Exception as exc:
        logger.warning("Redis health check probe failed: %s", exc)
        return False


async def dispose_app_redis(app: Any) -> None:
    """Dispose only the Redis client and pool belonging to the supplied application instance."""
    redis_client = getattr(app.state, "redis_client", None)
    if redis_client is not None:
        try:
            if hasattr(redis_client, "aclose"):
                await redis_client.aclose()
            elif hasattr(redis_client, "close"):
                await redis_client.close()
        except Exception as exc:
            logger.warning("Error closing application Redis client: %s", exc)

        try:
            pool = getattr(redis_client, "connection_pool", None)
            if pool is not None and hasattr(pool, "disconnect"):
                await pool.disconnect()
        except Exception as exc:
            logger.warning("Error disconnecting application Redis pool: %s", exc)

        app.state.redis_client = None


async def close_redis_connections() -> None:
    """Cleanly close global Redis connections during standalone script shutdown."""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


def close_sync_redis_connections() -> None:
    """Cleanly close global synchronous Redis connections during worker/script shutdown."""
    global _sync_redis_client, _sync_redis_pool
    if _sync_redis_client is not None:
        _sync_redis_client.close()
        _sync_redis_client = None
    if _sync_redis_pool is not None:
        _sync_redis_pool.disconnect()
        _sync_redis_pool = None
