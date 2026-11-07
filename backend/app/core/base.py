"""Declarative Base, metadata naming conventions, and common mixins for SQLAlchemy 2.x."""

from datetime import datetime
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


class Base(AsyncAttrs, DeclarativeBase):
    """Abstract base model declaring standard metadata and naming conventions."""

    metadata = metadata


class TimestampMixin:
    """Standardized UTC timestamps using PostgreSQL TIMESTAMPTZ."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
    )


class TenantScopedMixin:
    """Multi-tenant isolation column enforcing mandatory tenant ownership."""

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
