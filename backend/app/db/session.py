"""SQLAlchemy 2.x asynchronous database engine, session lifecycle, and transaction management.

Re-exports core database operations while preserving unified singleton instances.
"""

from __future__ import annotations

from app.core.database import (
    check_database_health,
    close_database_connections,
    create_db_engine,
    create_session_factory,
    dispose_app_database,
    get_db,
    get_engine,
    get_session_factory,
    transactional_session,
)
from app.db.events import register_pool_cleanup_listener

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
