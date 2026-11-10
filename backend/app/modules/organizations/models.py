"""SQLAlchemy models for multi-tenant organizations, roles, permissions, and memberships."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin, generate_uuid7, utc_now


class Organization(Base, TimestampMixin):
    """Platform-Global root tenant entity (Architecture Document 05 Table 1)."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", server_default="active"
    )
    pipeline_stages: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership", back_populates="organization", cascade="all, delete-orphan"
    )
    custom_roles: Mapped[list["Role"]] = relationship(
        "Role", back_populates="organization", cascade="all, delete-orphan"
    )


class Role(Base, TimestampMixin):
    """Platform-Global and Tenant-Custom Role definitions (Architecture Document 08)."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_id_name"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="custom_roles"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership", back_populates="role"
    )


class Permission(Base, TimestampMixin):
    """Platform-Global capability codes (Architecture Document 08)."""

    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Relationships
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """Mapping of roles to authorized permissions."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    role_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    role: Mapped[Role] = relationship("Role", back_populates="role_permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="role_permissions")


class OrganizationMembership(Base, TimestampMixin):
    """Tenant-scoped membership associating users with organizations and roles.

    Enforces Tenant-Scoped Table 1 requirements from DATABASE_SECURITY_INVENTORY.md.
    """

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", name="uq_organization_memberships_tenant_id_user_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="memberships")
    role: Mapped[Role] = relationship("Role", back_populates="memberships")
