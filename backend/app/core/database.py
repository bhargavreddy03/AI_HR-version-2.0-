"""SQLAlchemy 2.x asynchronous database engine, session lifecycle, and pool safety."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

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


def register_pool_cleanup_listener(engine: AsyncEngine) -> None:
    """Register pool checkin defense-in-depth cleanup listener for PostgreSQL connections.

    Transaction-local tenant contexts (set_config(..., true)) are naturally and automatically
    reverted by PostgreSQL at transaction COMMIT or ROLLBACK.
    As defense-in-depth against deliberate or accidental session-scoped tenant leaks (is_local=false),
    this listener resets app.current_tenant_id upon connection checkin and commits the reset.
    If any error occurs during cleanup, the connection is invalidated immediately to prevent reuse.
    """

    @event.listens_for(engine.sync_engine, "checkin")
    def on_connection_checkin(dbapi_connection: Any, connection_record: Any) -> None:
        if engine.dialect.name == "postgresql":
            try:
                if hasattr(dbapi_connection, "cursor"):
                    cursor = dbapi_connection.cursor()
                    try:
                        cursor.execute("SELECT set_config('app.current_tenant_id', '', false);")
                        if hasattr(dbapi_connection, "commit"):
                            dbapi_connection.commit()
                    finally:
                        if hasattr(cursor, "close"):
                            cursor.close()
            except Exception as exc:
                logger.error(
                    "Failed to reset tenant context on connection checkin: %s. Invalidating connection.",
                    exc,
                )
                connection_record.invalidate(exc)
                raise


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
    register_pool_cleanup_listener(engine)
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
    """Return the global cached AsyncEngine instance or initialize a new one.

    Safely disposes of any previous engine pool when database configuration changes.
    Preserves simple singleton defaults for standalone CLI and script execution.
    """
    global _engine, _session_factory
    cfg = settings or get_settings()

    if _engine is None or str(_engine.url) != cfg.DATABASE_URL:
        if _engine is not None:
            try:
                _engine.sync_engine.dispose()
            except Exception as exc:
                logger.warning("Error disposing previous engine sync pool: %s", exc)
        _engine = create_db_engine(cfg)
        _session_factory = None

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
    request: Request = cast(Request, None),
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
                engine = create_db_engine(app_settings)
                request.app.state.engine = engine
            if engine is not None:
                factory = create_session_factory(engine)
                request.app.state.session_factory = factory

    if factory is None:
        factory = get_session_factory()

    session = factory()
    if hasattr(session, "__aenter__"):
        async with session as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    else:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def transactional_session(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    engine: AsyncEngine | None = None,
    settings: Settings | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Explicit transaction context manager for background workers, tasks, and scripts.

    Context manager lifecycle ordering:
    1. Create the session from factory.
    2. Begin the transaction block via session.begin().
    3. Yield the session to the caller.
    4. Automatically commits on successful exit of transaction block.
    5. Rolls back on failure (guaranteeing clean rollback without redundant conflicting calls).
    6. Closes the session strictly AFTER transaction completion.
    """
    factory = session_factory or get_session_factory(engine=engine, settings=settings)
    raw = factory()
    if hasattr(raw, "__aenter__"):
        session_ctx = raw
    else:

        @asynccontextmanager
        async def _wrap(s: Any) -> AsyncGenerator[Any, None]:
            yield s

        session_ctx = _wrap(raw)

    async with session_ctx as session:
        try:
            try:
                async with session.begin():
                    yield session
            except Exception:
                if hasattr(session, "in_transaction") and not session.in_transaction():
                    pass
                else:
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


async def dispose_app_database(app: Any) -> None:
    """Dispose only the database engine and session factory belonging to the supplied application instance."""
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
        app.state.engine = None
        app.state.session_factory = None


async def close_database_connections() -> None:
    """Cleanly dispose of global connection pool during standalone script shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


__all__ = [
    "check_database_health",
    "close_database_connections",
    "create_db_engine",
    "create_session_factory",
    "dispose_app_database",
    "get_db",
    "get_engine",
    "get_session_factory",
    "register_pool_cleanup_listener",
    "transactional_session",
]
