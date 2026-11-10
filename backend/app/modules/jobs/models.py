"""SQLAlchemy models for Job Requisitions and Candidate Job Applications.

Conforms to Step 4.1 Candidate Portal and Multi-Tenant Isolation Architecture.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
from app.modules.auth.models import User


class JobStatus(str, enum.Enum):
    """Lifecycle status for a job opening."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


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
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_qualifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_required: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    experience_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mid"
    )  # entry, mid, senior, lead, executive
    experience_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vacancies_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recruiter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    hiring_manager_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(50), nullable=False, default="public", index=True
    )  # public, internal, unlisted
    approval_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )  # draft, pending, approved, rejected
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=JobStatus.PUBLISHED.value, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, default=utc_now
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reopened_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    change_request_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_deadline: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    recruiter: Mapped[User | None] = relationship(
        "User", foreign_keys=[recruiter_id], lazy="selectin"
    )
    hiring_manager: Mapped[User | None] = relationship(
        "User", foreign_keys=[hiring_manager_id], lazy="selectin"
    )
    applications: Mapped[list[JobApplication]] = relationship(
        "JobApplication", back_populates="job", cascade="all, delete-orphan"
    )
    lifecycle_history: Mapped[list[JobLifecycleHistory]] = relationship(
        "JobLifecycleHistory",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="desc(JobLifecycleHistory.created_at)",
    )
    assignment_history: Mapped[list[JobAssignmentHistory]] = relationship(
        "JobAssignmentHistory",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="desc(JobAssignmentHistory.created_at)",
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
    resume_version_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resume_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
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
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    consent_records: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    timeline: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    audit_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    applied_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="applications")
    stage_history: Mapped[list[ApplicationStageHistory]] = relationship(
        "ApplicationStageHistory",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(ApplicationStageHistory.created_at)",
    )
    notes: Mapped[list[CandidateInternalNote]] = relationship(
        "CandidateInternalNote",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(CandidateInternalNote.created_at)",
    )
    review_feedback: Mapped[list[CandidateReviewFeedback]] = relationship(
        "CandidateReviewFeedback",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(CandidateReviewFeedback.created_at)",
    )
    tasks: Mapped[list[CandidateRecruitmentTask]] = relationship(
        "CandidateRecruitmentTask",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(CandidateRecruitmentTask.created_at)",
    )


class JobLifecycleHistory(Base, TenantScopedMixin):
    """Immutable audit log of all job requisition lifecycle state transitions."""

    __tablename__ = "job_lifecycle_history"

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
    previous_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="lifecycle_history")
    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_id], lazy="selectin")


class ApplicationStageHistory(Base, TenantScopedMixin):
    """Immutable audit trail of all candidate application recruitment pipeline stage transitions."""

    __tablename__ = "application_stage_history"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    new_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Relationships
    application: Mapped[JobApplication] = relationship("JobApplication", back_populates="stage_history")
    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_id], lazy="selectin")


class JobAssignmentHistory(Base, TenantScopedMixin):
    """Immutable audit trail of recruiter and hiring manager job assignments."""

    __tablename__ = "job_assignment_history"

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
    assignment_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # recruiter, hiring_manager
    actor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    previous_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="assignment_history")
    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_id], lazy="selectin")
    previous_user: Mapped[User | None] = relationship("User", foreign_keys=[previous_user_id], lazy="selectin")
    new_user: Mapped[User | None] = relationship("User", foreign_keys=[new_user_id], lazy="selectin")


class CandidateInternalNote(Base, TenantScopedMixin, TimestampMixin):
    """Internal recruiter and hiring manager notes strictly private to organization."""

    __tablename__ = "candidate_internal_notes"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general", server_default="general"
    )
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    application: Mapped[JobApplication | None] = relationship(
        "JobApplication", back_populates="notes"
    )
    candidate: Mapped[User] = relationship("User", foreign_keys=[candidate_id], lazy="selectin")
    author: Mapped[User | None] = relationship("User", foreign_keys=[author_id], lazy="selectin")


class CandidateReviewFeedback(Base, TenantScopedMixin, TimestampMixin):
    """Structured collaborative evaluation feedback / scorecards from hiring team."""

    __tablename__ = "candidate_review_feedback"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)  # strong_yes, yes, neutral, no, strong_no
    technical_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cultural_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    pros: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    cons: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)

    # Relationships
    application: Mapped[JobApplication] = relationship(
        "JobApplication", back_populates="review_feedback"
    )
    reviewer: Mapped[User] = relationship("User", foreign_keys=[reviewer_id], lazy="selectin")


class CandidateRecruitmentTask(Base, TenantScopedMixin, TimestampMixin):
    """Internal recruitment action items and follow-up tasks linked to candidate applications."""

    __tablename__ = "candidate_recruitment_tasks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    creator_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    creator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general", server_default="general"
    )
    due_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    application: Mapped[JobApplication | None] = relationship(
        "JobApplication", back_populates="tasks"
    )
    candidate: Mapped[User] = relationship("User", foreign_keys=[candidate_id], lazy="selectin")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[creator_id], lazy="selectin")
    assignee: Mapped[User | None] = relationship("User", foreign_keys=[assignee_id], lazy="selectin")




