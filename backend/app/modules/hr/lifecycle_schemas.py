"""Pydantic v2 schemas for HR Job Lifecycle, Publishing, and Approval Workflows.

Conforms strictly to Step 4.2.4 specifications.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.hr.requisition_schemas import JobRequisitionRead


class JobLifecycleActionRequest(BaseModel):
    """Payload for executing a lifecycle state transition."""

    model_config = ConfigDict(from_attributes=True)

    action: str = Field(
        ...,
        description=(
            "Action to perform: submit_for_approval, approve, request_changes, "
            "publish, pause, reopen, close, archive, return_to_draft"
        ),
    )
    reason: str | None = Field(
        None,
        description="Reason or change feedback (mandatory for request_changes, optional for others)",
    )
    audit_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Supplementary structured audit metadata",
    )


class JobLifecycleHistoryItem(BaseModel):
    """Immutable audit entry recording a single lifecycle transition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    previous_status: str
    new_status: str
    action: str
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    reason: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class JobLifecyclePermittedActionsResponse(BaseModel):
    """Evaluation of permitted actions for the calling user on a requisition."""

    job_id: UUID
    current_status: str
    approval_status: str
    permitted_actions: list[str]
    can_approve: bool
    separation_of_duties_active: bool


class JobLifecycleTransitionResponse(BaseModel):
    """Response returned upon successful execution of a lifecycle transition."""

    job: JobRequisitionRead
    transition: JobLifecycleHistoryItem
    permitted_next_actions: list[str]
