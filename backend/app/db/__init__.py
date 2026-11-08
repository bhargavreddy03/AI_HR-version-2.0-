"""Database module exports for PostgreSQL 16, SQLAlchemy 2.x, and pgvector."""

from app.core.security import set_tenant_context
from app.db.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TenantScopedMixin,
    TimestampMixin,
    generate_uuid7,
    metadata,
    utc_now,
)
from app.db.events import register_pool_cleanup_listener
from app.db.session import (
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

__all__ = [
    "POSTGRES_NAMING_CONVENTION",
    "Base",
    "TenantScopedMixin",
    "TimestampMixin",
    "check_database_health",
    "close_database_connections",
    "create_db_engine",
    "create_session_factory",
    "dispose_app_database",
    "generate_uuid7",
    "get_db",
    "get_engine",
    "get_session_factory",
    "metadata",
    "register_pool_cleanup_listener",
    "set_tenant_context",
    "transactional_session",
    "utc_now",
]
