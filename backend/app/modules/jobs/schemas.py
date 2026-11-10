"""Pydantic v2 schemas for Job Discovery and Candidate Job Applications.

Conforms to Step 4.1 candidate experience and application workflow specifications.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# -----------------------------------------------------------------------------
# Job Discovery Schemas
# -----------------------------------------------------------------------------
class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    tenant_id: UUID
    organization_name: str | None = None
    title: str
    slug: str
    department: str
    location: str
    remote_type: str
    employment_type: str
    description: str
    requirements: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    experience_level: str
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    status: str
    published_at: datetime | None = None
    application_deadline: datetime | None = None
    is_saved: bool = False
    has_applied: bool = False
    is_expired: bool = False

    @model_validator(mode="after")
    def populate_aliases(self) -> JobRead:
        if not self.required_skills and self.skills_required:
            self.required_skills = self.skills_required
        return self


class JobListResponse(BaseModel):
    jobs: list[JobRead]
    total: int
    page: int
    page_size: int
    total_pages: int


# -----------------------------------------------------------------------------
# Saved Job Schemas
# -----------------------------------------------------------------------------
class SavedJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID | None = None
    job_id: UUID
    saved_at: datetime
    job: JobRead

    @model_validator(mode="after")
    def populate_id(self) -> SavedJobRead:
        if not self.id:
            self.id = self.job_id
        return self


# -----------------------------------------------------------------------------
# Job Application Schemas
# -----------------------------------------------------------------------------
class JobApplyRequest(BaseModel):
    resume_id: UUID | None = Field(
        None, description="Optional specific candidate resume ID; defaults to active default resume"
    )
    cover_letter: str | None = Field(None, max_length=5000)


class JobApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    candidate_id: UUID
    tenant_id: UUID
    organization_name: str | None = None
    job_title: str
    job_department: str
    job_location: str
    remote_type: str | None = None
    resume_id: UUID | None = None
    resume_filename: str | None = None
    resume_snapshot_sha256: str
    status: str
    candidate_status: str
    cover_letter: str | None = None
    applied_at: datetime
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None


class ApplicationWithdrawRequest(BaseModel):
    reason: str = Field(
        ..., min_length=3, max_length=500, description="Mandatory reason for withdrawal"
    )


class ApplicationSubmitResponse(BaseModel):
    id: UUID
    job_id: UUID
    candidate_status: str
    message: str = "Application submitted successfully"
    applied_at: datetime
