"""SQLAlchemy models for Job Requisitions and Candidate Job Applications.

Conforms to Step 4.1 Candidate Portal and Multi-Tenant Isolation Architecture.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TenantScopedMixin, TimestampMixin, generate_uuid7, utc_now


class JobStatus(str, enum.Enum):
    """Lifecycle status for a job opening."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class CandidateFacingStatus(str, enum.Enum):
    """Candidate-safe lifecycle statuses displayed in candidate tracking portal."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    IN_SCREENING = "in_screening"
    INTERVIEW_STAGE = "interview_stage"
    OFFER_STAGE = "offer_stage"
    NOT_SELECTED = "not_selected"
    WITHDRAWN = "withdrawn"


class Job(Base, TenantScopedMixin, TimestampMixin):
    """Job requisition published by an employer organization."""

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    remote_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="onsite", index=True
    )  # remote, hybrid, onsite
    employment_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="full_time", index=True
    )  # full_time, part_time, contract, internship
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_required: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    experience_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mid"
    )  # entry, mid, senior, lead, executive
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=JobStatus.PUBLISHED.value, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, default=utc_now
    )
    application_deadline: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    applications: Mapped[list[JobApplication]] = relationship(
        "JobApplication", back_populates="job", cascade="all, delete-orphan"
    )


class JobApplication(Base, TenantScopedMixin, TimestampMixin):
    """Formal candidate application submitted to a specific job opening.

    Preserves immutable evidence reference (resume_snapshot_sha256) and prevents duplicate active submissions.
    """

    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_job_applications_candidate_job"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("candidate_resumes.id", ondelete="SET NULL"),
        nullable=True,
    )
    resume_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="submitted", index=True
    )  # Internal ATS status
    candidate_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CandidateFacingStatus.SUBMITTED.value,
        index=True,
    )  # Candidate portal facing status
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="applications")
