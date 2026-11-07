"""SQLAlchemy 2.x asynchronous database engine, session lifecycle, and pool safety."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the global cached AsyncEngine instance or initialize a new one."""
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_async_engine(
            cfg.DATABASE_URL,
            echo=cfg.DEBUG,
            pool_size=cfg.DB_POOL_SIZE,
            max_overflow=cfg.DB_MAX_OVERFLOW,
            pool_timeout=cfg.DB_POOL_TIMEOUT,
            pool_recycle=cfg.DB_POOL_RECYCLE,
            pool_pre_ping=True,
        )

        # Connection Pool Defense-in-Depth Reset Listener (Architecture 04 Section 4)
        # Prevents cross-tenant context bleeding when reusing pooled connections
        @event.listens_for(_engine.sync_engine, "reset")
        def on_connection_reset(dbapi_connection: Any, connection_record: Any) -> None:
            try:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.current_tenant_id', '', false);")
            except Exception:
                # SQLite or non-Postgres test engines may not support set_config
                pass

    return _engine


def get_session_factory(
    engine: AsyncEngine | None = None, settings: Settings | None = None
) -> async_sessionmaker[AsyncSession]:
    """Return the global cached async_sessionmaker factory."""
    global _session_factory
    if _session_factory is None:
        eng = engine or get_engine(settings=settings)
        _session_factory = async_sessionmaker(
            bind=eng,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated, transaction-managed AsyncSession.

    Commits on success; automatically rolls back on any exception before closing.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health(engine: AsyncEngine | None = None) -> bool:
    """Perform a live database probe (SELECT 1) with timeout protection."""
    eng = engine or get_engine()
    try:
        async with asyncio.timeout(3.0):
            async with eng.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
    except Exception as exc:
        logger.warning("Database health check probe failed: %s", exc)
        return False


async def close_database_connections() -> None:
    """Cleanly dispose of connection pool during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
