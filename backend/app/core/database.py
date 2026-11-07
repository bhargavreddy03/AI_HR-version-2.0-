"""SQLAlchemy 2.x asynchronous database engine, session lifecycle, and pool safety."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
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


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Create and configure a new AsyncEngine instance with pool safety listeners."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
    )

    # Connection Pool Defense-in-Depth Checkin Listener (Architecture 04 Section 4)
    # Transaction-local settings (is_local=true) are automatically reverted by PostgreSQL
    # upon transaction commit or rollback. This checkin hook provides defense-in-depth
    # against accidental session-scoped settings on PostgreSQL connections.
    # If clearing fails, the connection record is invalidated so tainted connections are never reused.
    @event.listens_for(engine.sync_engine, "checkin")
    def on_connection_checkin(dbapi_connection: Any, connection_record: Any) -> None:
        if engine.dialect.name == "postgresql":
            try:
                if hasattr(dbapi_connection, "cursor"):
                    with dbapi_connection.cursor() as cursor:
                        cursor.execute("SELECT set_config('app.current_tenant_id', '', false);")
            except Exception as exc:
                logger.error(
                    "Failed to reset tenant context on connection checkin: %s. Invalidating connection.",
                    exc,
                )
                connection_record.invalidate(exc)
                raise

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a new async_sessionmaker bound to the supplied engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the global cached AsyncEngine instance or initialize a new one."""
    global _engine
    cfg = settings or get_settings()

    if _engine is None or str(_engine.url) != cfg.DATABASE_URL:
        _engine = create_db_engine(cfg)

    return _engine


def get_session_factory(
    engine: AsyncEngine | None = None, settings: Settings | None = None
) -> async_sessionmaker[AsyncSession]:
    """Return the global cached async_sessionmaker factory."""
    global _session_factory
    eng = engine or get_engine(settings=settings)

    if _session_factory is None or _session_factory.kw.get("bind") != eng:
        _session_factory = create_session_factory(eng)

    return _session_factory


async def get_db(
    request: Request | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated, transaction-managed AsyncSession.

    Prefers the session factory configured on the active application instance (request.app.state)
    to prevent cross-application configuration leakage, falling back to the global factory.
    Commits on success; automatically rolls back on any exception before closing.
    """
    factory: async_sessionmaker[AsyncSession] | None = None

    if request is not None and hasattr(request, "app"):
        factory = getattr(request.app.state, "session_factory", None)
        if factory is None:
            app_settings = getattr(request.app.state, "settings", None)
            engine = getattr(request.app.state, "engine", None)
            if engine is None and app_settings is not None:
                engine = get_engine(app_settings)
                request.app.state.engine = engine
            if engine is not None:
                factory = get_session_factory(engine=engine, settings=app_settings)
                request.app.state.session_factory = factory

    if factory is None:
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


async def check_database_health(
    engine: AsyncEngine | None = None,
    settings: Settings | None = None,
) -> bool:
    """Perform a live database probe (SELECT 1) with timeout protection."""
    eng = engine or get_engine(settings=settings)
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
