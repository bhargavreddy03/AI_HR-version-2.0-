"""Declarative Base, metadata naming conventions, and common mixins for SQLAlchemy 2.x."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Canonical PostgreSQL constraint naming convention conforming to Step 2 architecture
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def generate_uuid7() -> uuid.UUID:
    """Generate an RFC 9562 compliant, time-ordered UUIDv7.

    Layout:
    - 48 bits: Unix timestamp in milliseconds
    - 4 bits: Version 7 (0b0111)
    - 12 bits: Random data (rand_a)
    - 2 bits: RFC 4122 Variant (0b10)
    - 62 bits: Cryptographically secure random data (rand_b)
    """
    ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)
    b = bytearray(16)
    b[0:6] = ms.to_bytes(6, "big")
    b[6] = 0x70 | (rand_bytes[0] & 0x0F)
    b[7] = rand_bytes[1]
    b[8] = 0x80 | (rand_bytes[2] & 0x3F)
    b[9:16] = rand_bytes[3:10]
    return uuid.UUID(bytes=bytes(b))


class Base(AsyncAttrs, DeclarativeBase):
    """Abstract base model declaring standard metadata and naming conventions."""

    metadata = metadata


class TimestampMixin:
    """Standardized UTC timestamps using PostgreSQL TIMESTAMPTZ.

    Eliminates naive datetimes by providing timezone-aware Python UTC defaults
    and relying on PostgreSQL-side CURRENT_TIMESTAMP server defaults.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=utc_now,
    )


class TenantScopedMixin:
    """Multi-tenant isolation column enforcing mandatory tenant ownership."""

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )


# Explicit model registration for Alembic metadata discovery
def import_all_models() -> None:
    """Explicitly import all domain models to ensure registration in Base.metadata."""
    import app.modules.auth.models  # noqa: F401
    import app.modules.embeddings.models  # noqa: F401
    import app.modules.organizations.models  # noqa: F401
