"""Pydantic v2 schemas for Candidate Portal data transfer objects.

Conforms to Step 4.1 candidate API specifications.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# Experience Schemas
# -----------------------------------------------------------------------------
class ExperienceBase(BaseModel):
    job_title: str = Field(..., min_length=1, max_length=150)
    company_name: str = Field(..., min_length=1, max_length=150)
    location: str | None = Field(None, max_length=150)
    start_date: str = Field(..., min_length=4, max_length=50)
    end_date: str | None = Field(None, max_length=50)
    is_current: bool = False
    description: str | None = None
    skills: list[str] = Field(default_factory=list)


class ExperienceCreate(ExperienceBase):
    pass


class ExperienceUpdate(BaseModel):
    job_title: str | None = Field(None, max_length=150)
    company_name: str | None = Field(None, max_length=150)
    location: str | None = Field(None, max_length=150)
    start_date: str | None = Field(None, max_length=50)
    end_date: str | None = Field(None, max_length=50)
    is_current: bool | None = None
    description: str | None = None
    skills: list[str] | None = None


class ExperienceRead(ExperienceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Education Schemas
# -----------------------------------------------------------------------------
class EducationBase(BaseModel):
    institution: str = Field(..., min_length=1, max_length=200)
    degree: str = Field(..., min_length=1, max_length=150)
    field_of_study: str = Field(..., min_length=1, max_length=150)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    grade: str | None = Field(None, max_length=50)


class EducationCreate(EducationBase):
    pass


class EducationUpdate(BaseModel):
    institution: str | None = Field(None, max_length=200)
    degree: str | None = Field(None, max_length=150)
    field_of_study: str | None = Field(None, max_length=150)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    grade: str | None = Field(None, max_length=50)


class EducationRead(EducationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Certification Schemas
# -----------------------------------------------------------------------------
class CertificationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    issuing_organization: str = Field(..., min_length=1, max_length=200)
    issue_date: str | None = Field(None, max_length=50)
    expiration_date: str | None = Field(None, max_length=50)
    credential_id: str | None = Field(None, max_length=100)
    credential_url: str | None = Field(None, max_length=512)


class CertificationCreate(CertificationBase):
    pass


class CertificationRead(CertificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Project Schemas
# -----------------------------------------------------------------------------
class ProjectBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    role: str | None = Field(None, max_length=100)
    project_url: str | None = Field(None, max_length=512)
    skills: list[str] = Field(default_factory=list)


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Language Schemas
# -----------------------------------------------------------------------------
class LanguageBase(BaseModel):
    language: str = Field(..., min_length=1, max_length=100)
    proficiency: str = Field(default="professional", max_length=50)


class LanguageCreate(LanguageBase):
    pass


class LanguageRead(LanguageBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Skills Schemas
# -----------------------------------------------------------------------------
class CandidateSkillsUpdate(BaseModel):
    skills: list[str] = Field(..., min_length=0, max_length=100)


class CandidateSkillsResponse(BaseModel):
    skills: list[str]
    total_count: int
    normalized_skills: list[str]


# -----------------------------------------------------------------------------
# Preference Schemas
# -----------------------------------------------------------------------------
class CandidatePreferenceBase(BaseModel):
    desired_job_titles: list[str] = Field(default_factory=list)
    desired_locations: list[str] = Field(default_factory=list)
    remote_preference: str = Field(default="flexible", max_length=50)
    employment_types: list[str] = Field(default_factory=lambda: ["full_time"])
    minimum_salary: int | None = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=10)


class CandidatePreferenceRead(CandidatePreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    updated_at: datetime


class CandidatePreferenceUpdate(BaseModel):
    desired_job_titles: list[str] | None = None
    desired_locations: list[str] | None = None
    remote_preference: str | None = Field(None, max_length=50)
    employment_types: list[str] | None = None
    minimum_salary: int | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=10)


# -----------------------------------------------------------------------------
# Profile Aggregated Schemas
# -----------------------------------------------------------------------------
class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    is_verified: bool = True
    headline: str | None = None
    bio: str | None = None
    phone: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    preferred_title: str | None = None
    work_authorization: str | None = None
    portfolio_urls: list[str] = Field(default_factory=list)
    self_declared_skills: list[str] = Field(default_factory=list)
    experiences: list[ExperienceRead] = Field(default_factory=list)
    educations: list[EducationRead] = Field(default_factory=list)
    certifications: list[CertificationRead] = Field(default_factory=list)
    projects: list[ProjectRead] = Field(default_factory=list)
    languages: list[LanguageRead] = Field(default_factory=list)
    preferences: CandidatePreferenceRead | None = None
    profile_completion_percentage: int = 0


class CandidateProfileUpdate(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    avatar_url: str | None = Field(None, max_length=512)
    headline: str | None = Field(None, max_length=255)
    bio: str | None = None
    phone: str | None = Field(None, max_length=50)
    location_city: str | None = Field(None, max_length=100)
    location_country: str | None = Field(None, max_length=100)
    preferred_title: str | None = Field(None, max_length=150)
    work_authorization: str | None = Field(None, max_length=100)
    portfolio_urls: list[str] | None = None


# -----------------------------------------------------------------------------
# Resume Schemas
# -----------------------------------------------------------------------------
class CandidateResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    filename: str
    file_size_bytes: int
    content_sha256: str
    mime_type: str
    status: str
    version_number: int
    is_default: bool
    skills_extracted: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeUploadResponse(BaseModel):
    id: UUID
    filename: str
    file_size_bytes: int
    content_sha256: str
    status: str
    version_number: int
    is_default: bool
    is_duplicate: bool = False
    message: str = "Resume uploaded successfully and queued for processing"


class ResumeExtractionResponse(BaseModel):
    resume_id: UUID
    status: str
    extracted_text: str | None = None
    skills_extracted: list[str] = Field(default_factory=list)
    word_count: int = 0


class ResumeExtractedDataUpdate(BaseModel):
    extracted_text: str | None = None
    skills_extracted: list[str] | None = None


class ResumeDownloadUrlResponse(BaseModel):
    resume_id: UUID
    download_url: str
    expires_in_seconds: int = 900


# -----------------------------------------------------------------------------
# Notification Schemas
# -----------------------------------------------------------------------------
class CandidateNotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    message: str
    category: str
    is_read: bool
    action_url: str | None = None
    created_at: datetime


class CandidateNotificationsResponse(BaseModel):
    notifications: list[CandidateNotificationRead]
    unread_count: int
