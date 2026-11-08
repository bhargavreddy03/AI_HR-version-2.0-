"""SQLAlchemy connection pool event listeners and security cleanup."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


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
