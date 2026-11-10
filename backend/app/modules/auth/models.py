"""SQLAlchemy models for platform-global identity, candidate user profiles, sessions, and revocation outbox."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin, generate_uuid7, utc_now


class User(Base, TimestampMixin):
    """Platform-Global user identity anchor (Architecture Document 05 Table 2)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="chk_users_names",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # MFA and Credentials
    mfa_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_backup_codes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # OAuth Identity Federation
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Authorization Epoch & Barrier Flags
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    litigation_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    force_authoritative_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationships
    candidate_profile: Mapped["CandidateUserProfile | None"] = relationship(
        "CandidateUserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )


class CandidateUserProfile(Base, TimestampMixin):
    """Platform-Global / Candidate-Owned personal portfolio profile (Architecture Document 05 Table 3)."""

    __tablename__ = "candidate_user_profiles"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    portfolio_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    self_declared_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Relationships
    user: Mapped[User] = relationship(User, back_populates="candidate_profile")


class UserSession(Base, TimestampMixin):
    """Durable server-side session registry and refresh token lifecycle record."""

    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )

    # Relationships
    user: Mapped[User] = relationship(User, back_populates="sessions")
    token_history: Mapped[list["SessionTokenHistory"]] = relationship(
        "SessionTokenHistory", back_populates="session", cascade="all, delete-orphan"
    )


class SessionTokenHistory(Base):
    """Historical refresh token hashes for session-lifetime reuse detection."""

    __tablename__ = "session_token_history"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    session: Mapped[UserSession] = relationship("UserSession", back_populates="token_history")


class AuthRevocationOutbox(Base):
    """Transactional Invalidation Outbox DDL (Architecture Document 05 Section 4.B)."""

    __tablename__ = "auth_revocation_outbox"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="GLOBAL_LOGOUT, USER_SUSPENDED, PASSWORD_CHANGED, ROLE_CHANGED, ORG_SUSPENDED, MEMBERSHIP_REMOVED",
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="USER, ORGANIZATION, MEMBERSHIP"
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    new_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )
