"""Declarative Base, metadata naming conventions, and common mixins for SQLAlchemy 2.x.

Re-exports core declarative definitions from app.db.base for backward compatibility.
"""

from app.db.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TenantScopedMixin,
    TimestampMixin,
    generate_uuid7,
    metadata,
    utc_now,
)

__all__ = [
    "POSTGRES_NAMING_CONVENTION",
    "Base",
    "TenantScopedMixin",
    "TimestampMixin",
    "generate_uuid7",
    "metadata",
    "utc_now",
]
