"""Pydantic v2 schemas for HR Applicant and Candidate Management.

Conforms strictly to Step 4.2 multi-tenant architecture and Candidate Portal (Step 4.1) models.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicantListItem(BaseModel):
    """Organization-scoped applicant row in HR workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    candidate_phone: str | None = None
    candidate_headline: str | None = None
    candidate_location: str | None = None
    candidate_avatar_url: str | None = None
    job_id: UUID
    job_title: str
    job_department: str
    job_location: str
    status: str
    candidate_status: str
    applied_at: datetime
    skills: list[str] = Field(default_factory=list)
    experience_years: float = 0.0
    current_job_title: str | None = None
    current_company: str | None = None
    resume_available: bool = False
    resume_id: UUID | None = None
    resume_filename: str | None = None
    resume_snapshot_sha256: str | None = None
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    hiring_manager_id: UUID | None = None
    hiring_manager_name: str | None = None
    last_activity_at: datetime


class ApplicantListResponse(BaseModel):
    """Server-side paginated applicant listing."""

    items: list[ApplicantListItem]
    total: int
    page: int
    page_size: int
    pages: int


class CandidateDetailExperience(BaseModel):
    """Work experience entry in candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_title: str
    company_name: str
    location: str | None = None
    start_date: str
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None
    skills: list[str] = Field(default_factory=list)


class CandidateDetailEducation(BaseModel):
    """Education record in candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    institution: str
    degree: str
    field_of_study: str
    start_year: int | None = None
    end_year: int | None = None
    grade: str | None = None


class CandidateDetailCertification(BaseModel):
    """Certification record in candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    issuing_organization: str
    issue_date: str | None = None
    expiration_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class CandidateDetailProject(BaseModel):
    """Project record in candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    role: str | None = None
    project_url: str | None = None
    skills: list[str] = Field(default_factory=list)


class CandidateDetailLanguage(BaseModel):
    """Language record in candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    language: str
    proficiency: str


class OrganizationApplicationSummary(BaseModel):
    """Historical or active application within the current tenant organization."""

    model_config = ConfigDict(from_attributes=True)

    application_id: UUID
    job_id: UUID
    job_title: str
    department: str
    applied_at: datetime
    status: str
    candidate_status: str
    withdrawn_at: datetime | None = None


class TimelineEventItem(BaseModel):
    """Individual activity timeline event for an application."""

    status: str
    changed_at: str
    note: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    is_internal: bool = False


class ApplicationDetailContext(BaseModel):
    """Current application details when viewing candidate in context of a requisition."""

    application_id: UUID
    job_id: UUID
    job_title: str
    job_department: str
    job_location: str
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    hiring_manager_id: UUID | None = None
    hiring_manager_name: str | None = None
    status: str
    candidate_status: str
    applied_at: datetime
    cover_letter: str | None = None
    answers: dict = Field(default_factory=dict)
    resume_id: UUID | None = None
    resume_version_applied: int | None = None
    resume_snapshot_sha256: str | None = None
    resume_filename: str | None = None
    candidate_timeline: list[TimelineEventItem] = Field(default_factory=list)
    internal_timeline: list[TimelineEventItem] = Field(default_factory=list)


class CandidateDetailResponse(BaseModel):
    """Comprehensive candidate view scoped to authorized organization context."""

    candidate_id: UUID
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone_number: str | None = None
    avatar_url: str | None = None
    headline: str | None = None
    bio: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    preferred_title: str | None = None
    work_authorization: str | None = None
    portfolio_urls: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experience_years: float = 0.0
    experiences: list[CandidateDetailExperience] = Field(default_factory=list)
    educations: list[CandidateDetailEducation] = Field(default_factory=list)
    certifications: list[CandidateDetailCertification] = Field(default_factory=list)
    projects: list[CandidateDetailProject] = Field(default_factory=list)
    languages: list[CandidateDetailLanguage] = Field(default_factory=list)
    current_application: ApplicationDetailContext | None = None
    organization_application_history: list[OrganizationApplicationSummary] = Field(
        default_factory=list
    )


class ResumeSignedUrlResponse(BaseModel):
    """Time-limited presigned URL envelope for authorized resume access."""

    application_id: UUID
    candidate_id: UUID
    resume_id: UUID | None = None
    filename: str
    mime_type: str = "application/pdf"
    file_size_bytes: int = 0
    content_sha256: str
    download_url: str
    expires_in_seconds: int = 900


class CandidateComparisonItem(BaseModel):
    """Candidate comparison metrics for side-by-side evaluation."""

    application_id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    job_id: UUID
    job_title: str
    status: str
    applied_at: datetime
    experience_years: float = 0.0
    current_job_title: str | None = None
    current_company: str | None = None
    highest_education: str | None = None
    skills: list[str] = Field(default_factory=list)
    job_skills_required: list[str] = Field(default_factory=list)
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_percentage: float = 0.0
    resume_available: bool = False


class CandidateComparisonRequest(BaseModel):
    """Request payload to compare selected candidate applications."""

    application_ids: list[UUID] = Field(..., min_length=2, max_length=4)


class CandidateComparisonResponse(BaseModel):
    """Comparison matrix envelope."""

    job_id: UUID | None = None
    job_title: str | None = None
    candidates: list[CandidateComparisonItem]


class BulkRecruiterAssignRequest(BaseModel):
    """Request payload to bulk-assign recruiter to selected applications."""

    application_ids: list[UUID] = Field(..., min_length=1, max_length=50)
    recruiter_id: UUID


class BulkRecruiterAssignResponse(BaseModel):
    """Result of bulk recruiter assignment."""

    updated_count: int
    application_ids: list[UUID]
    recruiter_id: UUID
    recruiter_name: str
