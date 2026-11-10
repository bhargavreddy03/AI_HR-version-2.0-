"""SQLAlchemy models for candidate profile, experience, education, resumes, saved jobs, and notifications.

Conforms to Step 4.1 Candidate Portal Architecture.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin, generate_uuid7, utc_now


class CandidateResumeStatus(str, enum.Enum):
    """Controlled lifecycle states for candidate resume processing."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CandidateExperience(Base, TimestampMixin):
    """Work experience entry in a candidate's global profile."""

    __tablename__ = "candidate_experiences"

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
    job_title: Mapped[str] = mapped_column(String(150), nullable=False)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    start_date: Mapped[str] = mapped_column(String(50), nullable=False)
    end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class CandidateEducation(Base, TimestampMixin):
    """Educational record in a candidate's global profile."""

    __tablename__ = "candidate_educations"

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
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str] = mapped_column(String(150), nullable=False)
    field_of_study: Mapped[str] = mapped_column(String(150), nullable=False)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)


class CandidateCertification(Base, TimestampMixin):
    """Professional certification or license record."""

    __tablename__ = "candidate_certifications"

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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuing_organization: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expiration_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class CandidateProject(Base, TimestampMixin):
    """Key personal or open-source project showcasing portfolio work."""

    __tablename__ = "candidate_projects"

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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class CandidateLanguage(Base, TimestampMixin):
    """Language proficiency record."""

    __tablename__ = "candidate_languages"

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
    language: Mapped[str] = mapped_column(String(100), nullable=False)
    proficiency: Mapped[str] = mapped_column(
        String(50), nullable=False, default="professional"
    )  # native, fluent, professional, conversational, basic


class CandidatePreference(Base, TimestampMixin):
    """Job search and employment preferences for a candidate."""

    __tablename__ = "candidate_preferences"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    desired_job_titles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    desired_locations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    remote_preference: Mapped[str] = mapped_column(
        String(50), nullable=False, default="flexible"
    )  # remote, hybrid, onsite, flexible
    employment_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["full_time"]
    )  # full_time, part_time, contract, internship
    minimum_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    notification_preferences: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "email_application_updates": True,
            "email_interview_alerts": True,
            "email_job_recommendations": False,
            "in_app_alerts": True,
            "digest_frequency": "instant",
        },
    )
    privacy_preferences: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "profile_visibility": "applied_only",
            "allow_ai_matching": True,
            "data_retention_months": 24,
        },
    )


class CandidateResume(Base, TimestampMixin):
    """Candidate-owned resume document with extracted skills and text snapshot.

    Reuses Step 3.10 S3 Storage and extraction infrastructure while anchoring to candidate global identity.
    """

    __tablename__ = "candidate_resumes"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CandidateResumeStatus.UPLOADED.value, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_extracted: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CandidateSavedJob(Base):
    """Saved or bookmarked jobs by candidate."""

    __tablename__ = "candidate_saved_jobs"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    saved_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )


class CandidateNotification(Base, TimestampMixin):
    """In-app notifications targeted to a candidate."""

    __tablename__ = "candidate_notifications"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general"
    )  # application_update, interview_alert, job_alert, general
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="not_configured"
    )


class CandidatePrivacyRequest(Base, TimestampMixin):
    """Formal GDPR/CCPA candidate privacy and data subject rights requests."""

    __tablename__ = "candidate_privacy_requests"

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
    request_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # export, correction, deletion, consent_revocation
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, processing, completed, rejected
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
