"""Pydantic v2 schemas for HR / Recruiter Dashboard and Analytics.

Conforms strictly to Step 4.2 specifications.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HrDashboardMetrics(BaseModel):
    """Organization-scoped high-level recruitment metrics."""

    model_config = ConfigDict(from_attributes=True)

    total_candidates: int = Field(0, description="Distinct candidate applicants for this tenant")
    total_applications: int = Field(0, description="Total applications across all jobs")
    active_jobs: int = Field(0, description="Active published jobs accepting applications")
    published_jobs: int = Field(0, description="Total published job requisitions")
    draft_jobs: int = Field(0, description="Requisitions currently in draft or pending")
    applications_awaiting_review: int = Field(
        0, description="Applications awaiting recruiter review"
    )
    shortlisted_candidates: int = Field(0, description="Candidates advanced to shortlisted stage")
    scheduled_interviews: int = Field(0, description="Applications currently in interview stage")
    hired_candidates: int = Field(0, description="Candidates hired or offer accepted")
    pending_tasks: int = Field(0, description="Pending recruitment review tasks")


class FunnelStageCount(BaseModel):
    """Aggregate count and conversion percentage for a recruitment pipeline stage."""

    stage: str = Field(..., description="Pipeline stage identifier")
    label: str = Field(..., description="Human-readable stage label")
    count: int = Field(0, description="Candidate count in this stage")
    percentage: float = Field(0.0, description="Conversion percentage from total applications")


class ApplicationsOverTimePoint(BaseModel):
    """Time-series point for application submissions."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    applications_count: int = Field(0, description="Number of applications on this date")


class JobApplicationCount(BaseModel):
    """Application volume by specific job requisition."""

    job_id: str = Field(..., description="Job UUID")
    job_title: str = Field(..., description="Job title")
    department: str = Field(..., description="Department")
    status: str = Field(..., description="Job status")
    applications_count: int = Field(0, description="Total applications received")
    active_count: int = Field(0, description="Active applications in review or pipeline")


class DepartmentApplicationCount(BaseModel):
    """Applications aggregated by department."""

    department: str = Field(..., description="Department name")
    applications_count: int = Field(0, description="Applications for this department")
    open_jobs_count: int = Field(0, description="Open requisitions in department")


class RecentApplicantItem(BaseModel):
    """Summary item for recently applied candidates."""

    application_id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str
    job_id: str
    job_title: str
    department: str
    applied_at: str
    stage: str
    candidate_status: str
    resume_snapshot_sha256: str | None = None
    skills_count: int = 0
    top_skills: list[str] = Field(default_factory=list)


class RecentActivityItem(BaseModel):
    """Activity feed item representing recruitment lifecycle events."""

    id: str
    event_type: str
    title: str
    description: str
    candidate_name: str | None = None
    job_title: str | None = None
    timestamp: str
    actor_name: str | None = None


class HrDashboardOverviewResponse(BaseModel):
    """Comprehensive organization-scoped dashboard payload."""

    tenant_id: str
    organization_name: str
    metrics: HrDashboardMetrics
    recruitment_funnel: list[FunnelStageCount]
    applications_over_time: list[ApplicationsOverTimePoint]
    applications_by_job: list[JobApplicationCount]
    applications_by_department: list[DepartmentApplicationCount]
    recent_applicants: list[RecentApplicantItem]
    recent_activities: list[RecentActivityItem]
    active_filters: dict[str, Any] = Field(default_factory=dict)
