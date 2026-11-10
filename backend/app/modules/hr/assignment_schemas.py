"""Pydantic schemas for recruiter and hiring manager assignment workflows and workload visibility."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssignRecruiterRequest(BaseModel):
    """Payload to assign, change, or remove a job's lead recruiter."""

    model_config = ConfigDict(from_attributes=True)

    recruiter_id: UUID | None = Field(
        None, description="User UUID of authorized organization recruiter, or null to unassign"
    )
    reason: str | None = Field(
        None, max_length=500, description="Optional business reason or handover notes"
    )


class AssignHiringManagerRequest(BaseModel):
    """Payload to assign, change, or remove a job's hiring manager."""

    model_config = ConfigDict(from_attributes=True)

    hiring_manager_id: UUID | None = Field(
        None, description="User UUID of authorized organization hiring manager, or null to unassign"
    )
    reason: str | None = Field(
        None, max_length=500, description="Optional business reason or handover notes"
    )


class JobAssignmentUpdateRequest(BaseModel):
    """Combined update payload for job assignments."""

    model_config = ConfigDict(from_attributes=True)

    recruiter_id: UUID | None = None
    hiring_manager_id: UUID | None = None
    update_recruiter: bool = False
    update_hiring_manager: bool = False
    reason: str | None = Field(None, max_length=500)


class JobAssignmentUpdateResponse(BaseModel):
    """Response confirming assignment transition with updated roles."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    job_title: str
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    hiring_manager_id: UUID | None = None
    hiring_manager_name: str | None = None
    updated_at: datetime
    message: str


class JobAssignmentHistoryItem(BaseModel):
    """Immutable audit trail log entry for job recruitment assignment changes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    assignment_type: str  # "recruiter" or "hiring_manager"
    actor_id: UUID | None = None
    actor_name: str | None = None
    previous_user_id: UUID | None = None
    previous_user_name: str | None = None
    new_user_id: UUID | None = None
    new_user_name: str | None = None
    reason: str | None = None
    created_at: datetime


class UserWorkloadItem(BaseModel):
    """Workload aggregations and capacity indicators for a recruiter or hiring manager."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    name: str
    email: str
    role: str
    department_id: UUID | None = None
    assigned_jobs_count: int = 0
    active_jobs_count: int = 0
    total_applications_count: int = 0
    pending_reviews_count: int = 0
    active_interviews_count: int = 0
    workload_status: str = "balanced"  # "low", "balanced", "high", "critical"


class TeamWorkloadSummary(BaseModel):
    """High-level summary of organization recruitment assignments."""

    model_config = ConfigDict(from_attributes=True)

    total_team_members: int
    total_assigned_jobs: int
    total_unassigned_jobs: int
    total_active_applications: int


class TeamWorkloadResponse(BaseModel):
    """Aggregated team recruitment workload dashboard data."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    recruiters: list[UserWorkloadItem]
    hiring_managers: list[UserWorkloadItem]
    summary: TeamWorkloadSummary


class AssignedVacancyItem(BaseModel):
    """A job vacancy assigned to the current recruiter or hiring manager."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    department: str
    status: str
    work_arrangement: str
    vacancies: int
    active_applications_count: int
    pending_reviews_count: int
    scheduled_interviews_count: int
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    hiring_manager_id: UUID | None = None
    hiring_manager_name: str | None = None
    created_at: datetime


class AssignedVacanciesResponse(BaseModel):
    """List of vacancies assigned to the requesting user."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    vacancies: list[AssignedVacancyItem]
    total: int
