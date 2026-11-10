"""Pydantic schemas for candidate review, internal notes, scorecards, tasks, and unified timeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------
# Internal Notes Schemas
# ----------------------------------------------------------------------


class CreateInternalNoteRequest(BaseModel):
    """Payload to record an internal note on a candidate or application."""

    model_config = ConfigDict(from_attributes=True)

    application_id: UUID | None = Field(
        None, description="Optional application UUID to scope note context"
    )
    content: str = Field(..., min_length=1, max_length=10000, description="Internal note content")
    category: str = Field(
        "general",
        description="Category: general, screening, interview_feedback, compensation, reference_check",
    )
    is_confidential: bool = Field(
        False, description="Whether this note is confidential to author and org admins"
    )


class UpdateInternalNoteRequest(BaseModel):
    """Payload to update an internal note authored by the requesting user."""

    model_config = ConfigDict(from_attributes=True)

    content: str = Field(..., min_length=1, max_length=10000)
    category: str | None = None
    is_confidential: bool | None = None


class InternalNoteResponse(BaseModel):
    """Internal recruiter/hiring manager note response envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    application_id: UUID | None = None
    author_id: UUID | None = None
    author_name: str
    author_role: str
    content: str
    category: str
    is_confidential: bool
    can_edit: bool = False
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------
# Review Scorecard Feedback Schemas
# ----------------------------------------------------------------------


class SubmitReviewFeedbackRequest(BaseModel):
    """Payload to submit collaborative candidate review feedback / scorecard."""

    model_config = ConfigDict(from_attributes=True)

    recommendation: str = Field(
        ...,
        description="Recommendation: strong_yes, yes, neutral, no, strong_no",
    )
    technical_rating: int | None = Field(None, ge=1, le=5)
    communication_rating: int | None = Field(None, ge=1, le=5)
    cultural_rating: int | None = Field(None, ge=1, le=5)
    overall_rating: int | None = Field(None, ge=1, le=5)
    summary: str = Field(..., min_length=1, max_length=10000)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class ReviewFeedbackResponse(BaseModel):
    """Review evaluation feedback envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    reviewer_id: UUID
    reviewer_name: str
    reviewer_role: str
    recommendation: str
    technical_rating: int | None = None
    communication_rating: int | None = None
    cultural_rating: int | None = None
    overall_rating: int | None = None
    summary: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------
# Follow-Up Task Schemas
# ----------------------------------------------------------------------


class CreateRecruitmentTaskRequest(BaseModel):
    """Payload to create a recruitment follow-up task."""

    model_config = ConfigDict(from_attributes=True)

    application_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    task_type: str = Field(
        "general",
        description="Type: resume_review, schedule_interview, phone_screen, reference_check, send_offer, general",
    )
    assignee_id: UUID | None = None
    due_date: datetime | None = None


class UpdateRecruitmentTaskRequest(BaseModel):
    """Payload to update or mark completed a recruitment task."""

    model_config = ConfigDict(from_attributes=True)

    is_completed: bool | None = None
    title: str | None = None
    description: str | None = None
    assignee_id: UUID | None = None
    due_date: datetime | None = None


class RecruitmentTaskResponse(BaseModel):
    """Recruitment task envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    application_id: UUID | None = None
    creator_id: UUID | None = None
    creator_name: str
    assignee_id: UUID | None = None
    assignee_name: str | None = None
    title: str
    description: str | None = None
    task_type: str
    due_date: datetime | None = None
    is_completed: bool
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------
# Candidate Activity Timeline Schemas
# ----------------------------------------------------------------------


class CandidateTimelineItem(BaseModel):
    """An event in the candidate activity history, clearly separated by visibility."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    title: str
    description: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    is_internal: bool
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)


class CandidateActivityTimelineResponse(BaseModel):
    """Chronological activity timeline separating internal collaboration from candidate events."""

    model_config = ConfigDict(from_attributes=True)

    candidate_id: UUID
    application_id: UUID | None = None
    events: list[CandidateTimelineItem]
    total_events: int
