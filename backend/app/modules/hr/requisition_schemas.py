"""Pydantic v2 schemas for HR Job Requisition Management.

Conforms strictly to Step 4.2.3 specifications.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobRequisitionCreate(BaseModel):
    """Schema for creating a new job requisition draft or pending approval."""

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., min_length=2, max_length=255, description="Official job title")
    department: str = Field(..., min_length=1, max_length=100, description="Department name")
    location: str = Field(..., min_length=1, max_length=255, description="Job location / city")
    country: str | None = Field(None, max_length=100, description="Country")
    remote_type: str = Field(
        "onsite", description="Work arrangement: onsite, hybrid, or remote"
    )
    employment_type: str = Field(
        "full_time",
        description="Employment type: full_time, part_time, contract, or internship",
    )
    experience_level: str = Field(
        "mid", description="Experience level: entry, mid, senior, lead, executive"
    )
    description: str = Field(..., min_length=10, description="Comprehensive job overview")
    responsibilities: str | None = Field(None, description="Detailed core responsibilities")
    required_qualifications: str | None = Field(
        None, description="Required education, experience, and certifications"
    )
    skills_required: list[str] = Field(
        default_factory=list, description="Mandatory technical competencies"
    )
    preferred_skills: list[str] = Field(
        default_factory=list, description="Bonus / preferred technical competencies"
    )
    experience_requirements: str | None = Field(
        None, description="Detailed experience requirements (e.g. 5+ years backend)"
    )
    education_requirements: str | None = Field(
        None, description="Minimum education (e.g. Bachelor's in CS)"
    )
    salary_min: int | None = Field(None, ge=0, description="Minimum base salary")
    salary_max: int | None = Field(None, ge=0, description="Maximum base salary")
    salary_currency: str = Field("USD", max_length=10, description="Currency code (USD, EUR, GBP)")
    vacancies_count: int = Field(1, ge=1, le=1000, description="Target number of hires")
    application_deadline: datetime | None = Field(
        None, description="Requisition closing / application deadline"
    )
    recruiter_id: UUID | None = Field(None, description="Assigned lead recruiter UUID")
    hiring_manager_id: UUID | None = Field(None, description="Assigned hiring manager UUID")
    visibility: str = Field(
        "public", description="Job visibility: public, internal, or unlisted"
    )
    status: str = Field(
        "draft", description="Initial status: draft or pending_approval"
    )

    @model_validator(mode="after")
    def validate_salary_range(self) -> JobRequisitionCreate:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min cannot be greater than salary_max")
        return self


class JobRequisitionUpdate(BaseModel):
    """Schema for updating an existing job requisition."""

    model_config = ConfigDict(from_attributes=True)

    title: str | None = Field(None, min_length=2, max_length=255)
    department: str | None = Field(None, min_length=1, max_length=100)
    location: str | None = Field(None, min_length=1, max_length=255)
    country: str | None = Field(None, max_length=100)
    remote_type: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    description: str | None = Field(None, min_length=10)
    responsibilities: str | None = None
    required_qualifications: str | None = None
    skills_required: list[str] | None = None
    preferred_skills: list[str] | None = None
    experience_requirements: str | None = None
    education_requirements: str | None = None
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)
    salary_currency: str | None = Field(None, max_length=10)
    vacancies_count: int | None = Field(None, ge=1, le=1000)
    application_deadline: datetime | None = None
    recruiter_id: UUID | None = None
    hiring_manager_id: UUID | None = None
    visibility: str | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_salary_range(self) -> JobRequisitionUpdate:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min cannot be greater than salary_max")
        return self


class TeamMemberOption(BaseModel):
    """Organization member available for recruiter or hiring manager assignment."""

    id: UUID
    name: str
    email: str
    role: str


class CanonicalSkillSuggestion(BaseModel):
    """Skill suggestion from the canonical skills registry."""

    canonical_name: str
    category: str
    skill_id: str


class JobRequisitionRead(BaseModel):
    """Authorized comprehensive view of an organization job requisition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    slug: str
    department: str
    location: str
    country: str | None = None
    remote_type: str
    employment_type: str
    experience_level: str
    description: str
    responsibilities: str | None = None
    required_qualifications: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_requirements: str | None = None
    education_requirements: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    vacancies_count: int = 1
    status: str
    approval_status: str
    visibility: str
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    hiring_manager_id: UUID | None = None
    hiring_manager_name: str | None = None
    hiring_manager_email: str | None = None
    applications_count: int = 0
    published_at: datetime | None = None
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    change_request_reason: str | None = None
    application_deadline: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobRequisitionListResponse(BaseModel):
    """Paginated response envelope for HR job requisitions."""

    items: list[JobRequisitionRead]
    total: int
    page: int
    page_size: int
    pages: int
