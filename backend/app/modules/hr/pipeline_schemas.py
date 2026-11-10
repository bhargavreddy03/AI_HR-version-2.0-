"""Pydantic v2 schemas for Recruitment Pipeline and Stage Management.

Conforms strictly to Step 4.2.6 multi-tenant architecture and FSM specifications.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PipelineStageConfig(BaseModel):
    """Configuration for a single pipeline stage."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    order: int
    is_terminal: bool = False
    color: str | None = None


class PipelineCardItem(BaseModel):
    """Candidate card item for Kanban board display."""

    model_config = ConfigDict(from_attributes=True)

    application_id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    candidate_headline: str | None = None
    candidate_avatar_url: str | None = None
    job_id: UUID
    job_title: str
    job_department: str
    stage: str
    stage_version: int = 1
    applied_at: datetime
    last_activity_at: datetime
    recruiter_id: UUID | None = None
    recruiter_name: str | None = None
    skills: list[str] = Field(default_factory=list)
    resume_available: bool = False


class PipelineStageColumn(BaseModel):
    """Kanban board stage column envelope."""

    id: str
    label: str
    order: int
    is_terminal: bool = False
    count: int = 0
    cards: list[PipelineCardItem] = Field(default_factory=list)


class PipelineBoardResponse(BaseModel):
    """Complete Kanban recruitment pipeline board response."""

    tenant_id: UUID
    stages: list[PipelineStageColumn]
    total_candidates: int
    active_filters: dict[str, Any] = Field(default_factory=dict)


class StageTransitionRequest(BaseModel):
    """Payload to transition an application to a new recruitment stage."""

    target_stage: str = Field(..., description="Target pipeline stage key")
    expected_stage_version: int | None = Field(
        None, description="Expected stage version for optimistic concurrency control"
    )
    reason: str | None = Field(
        None, description="Mandatory reason for rejection; optional transition notes for others"
    )
    notes: str | None = Field(None, description="Internal evaluation notes")


class StageTransitionResponse(BaseModel):
    """Response returned upon successful stage transition."""

    application_id: UUID
    previous_stage: str
    new_stage: str
    stage_version: int
    candidate_status: str
    changed_at: datetime
    actor_name: str | None = None
    actor_role: str | None = None
    reason: str | None = None


class BulkStageMoveRequest(BaseModel):
    """Payload for safe bulk recruitment stage movement."""

    application_ids: list[UUID] = Field(..., min_length=1, max_length=50)
    target_stage: str = Field(..., description="Target stage for all selected applications")
    reason: str | None = Field(None, description="Reason or notes for transition")


class BulkStageMoveSkippedItem(BaseModel):
    """Details on why an application was ineligible for a bulk stage move."""

    application_id: UUID
    candidate_name: str | None = None
    current_stage: str
    reason: str


class BulkStageMoveResponse(BaseModel):
    """Summary of affected applications from bulk stage movement."""

    target_stage: str
    total_requested: int
    updated_count: int
    updated_ids: list[UUID]
    skipped_count: int
    skipped: list[BulkStageMoveSkippedItem]


class ApplicationStageHistoryItem(BaseModel):
    """Immutable audit log record for an application stage transition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    previous_stage: str
    new_stage: str
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    reason: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
