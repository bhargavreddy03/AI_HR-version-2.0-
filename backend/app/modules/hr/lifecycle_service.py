"""HR Job Lifecycle and Publishing domain service conforming strictly to Step 4.2.4.

Enforces:
- Deterministic finite state machine transitions.
- Multi-tier role permissions (Recruiter, Hiring Manager, Organization Admin).
- Separation of duties: assigned lead recruiter cannot approve their own requisition.
- Immutable lifecycle audit trail recording.
- Idempotent asynchronous notification dispatch via Celery.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AppException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
)
from app.modules.auth.models import User
from app.modules.hr.lifecycle_schemas import (
    JobLifecycleActionRequest,
    JobLifecycleHistoryItem,
    JobLifecyclePermittedActionsResponse,
    JobLifecycleTransitionResponse,
)
from app.modules.hr.service import hr_requisition_service
from app.modules.jobs.models import Job, JobLifecycleHistory, JobStatus

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Approved Business Rules & Finite State Machine Matrix
# ------------------------------------------------------------------------------

TRANSITION_RULES: dict[str, dict[str, dict[str, Any]]] = {
    JobStatus.DRAFT.value: {
        "submit_for_approval": {
            "target_status": JobStatus.PENDING_APPROVAL.value,
            "target_approval": "pending_approval",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
    },
    JobStatus.PENDING_APPROVAL.value: {
        "approve": {
            "target_status": JobStatus.APPROVED.value,
            "target_approval": "approved",
            "allowed_roles": {
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
            "enforce_separation_of_duties": True,
        },
        "request_changes": {
            "target_status": JobStatus.DRAFT.value,
            "target_approval": "changes_requested",
            "allowed_roles": {
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": True,
        },
    },
    JobStatus.APPROVED.value: {
        "publish": {
            "target_status": JobStatus.PUBLISHED.value,
            "target_approval": "published",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
        "return_to_draft": {
            "target_status": JobStatus.DRAFT.value,
            "target_approval": "draft",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
    },
    JobStatus.PUBLISHED.value: {
        "pause": {
            "target_status": JobStatus.PAUSED.value,
            "target_approval": "paused",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
        "close": {
            "target_status": JobStatus.CLOSED.value,
            "target_approval": "closed",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
    },
    JobStatus.PAUSED.value: {
        "reopen": {
            "target_status": JobStatus.PUBLISHED.value,
            "target_approval": "published",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
        "close": {
            "target_status": JobStatus.CLOSED.value,
            "target_approval": "closed",
            "allowed_roles": {
                "recruiter",
                "hiring_manager",
                "org_admin",
                "admin",
                "platform_super_admin",
            },
            "reason_required": False,
        },
    },
    JobStatus.CLOSED.value: {
        "archive": {
            "target_status": JobStatus.ARCHIVED.value,
            "target_approval": "archived",
            "allowed_roles": {
                "org_admin",
                "admin",
                "platform_super_admin",
                "recruiter",
            },
            "reason_required": False,
        },
    },
}


class HrJobLifecycleService:
    """Service handling job requisition state transitions, separation of duties, and audit logging."""

    async def execute_transition(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
        user_id: UUID,
        user_roles: list[str],
        request: JobLifecycleActionRequest,
        is_super_admin: bool = False,
    ) -> JobLifecycleTransitionResponse:
        """Execute and audit a job requisition lifecycle state transition."""
        # 1. Fetch Job and verify tenant isolation
        stmt = (
            select(Job)
            .options(selectinload(Job.recruiter), selectinload(Job.hiring_manager))
            .where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("JobRequisition", job_id)

        current_status = job.status
        action = request.action.strip().lower()

        # 2. Validate FSM Permitted Transition
        status_transitions = TRANSITION_RULES.get(current_status, {})
        if action not in status_transitions:
            allowed_actions = list(status_transitions.keys())
            raise ConflictException(
                f"Invalid lifecycle transition: action '{action}' is not permitted for a requisition "
                f"in '{current_status}' status. Permitted actions: {allowed_actions}"
            )

        rule = status_transitions[action]
        allowed_roles = rule["allowed_roles"]

        # 3. Role Permission Verification
        normalized_user_roles = {r.lower() for r in user_roles}
        # In test environments or fallback, if roles list is empty, default to checking org membership
        has_role = bool(normalized_user_roles.intersection(allowed_roles)) or is_super_admin
        if not has_role:
            raise AuthorizationException(
                f"Your assigned role does not permit executing lifecycle action '{action}'.",
                error_code="LIFECYCLE_ACTION_FORBIDDEN",
            )

        # 4. Enforce Separation of Duties
        if rule.get("enforce_separation_of_duties"):
            if job.recruiter_id and user_id == job.recruiter_id and not is_super_admin:
                raise AuthorizationException(
                    "Separation of duties policy forbids the assigned lead recruiter from approving their own job requisition.",
                    error_code="SEPARATION_OF_DUTIES_VIOLATION",
                )

        # 5. Enforce Mandatory Reason (e.g. Request Changes)
        reason_text = request.reason.strip() if request.reason else None
        if rule.get("reason_required") and (not reason_text or len(reason_text) < 3):
            raise AppException(
                message="A detailed reason is mandatory when requesting changes on a job requisition.",
                status_code=400,
                code="LIFECYCLE_REASON_REQUIRED",
                detail="A detailed reason is mandatory when requesting changes on a job requisition.",
            )

        # 6. Apply Transition Mutations
        target_status = rule["target_status"]
        target_approval = rule["target_approval"]

        job.status = target_status
        job.approval_status = target_approval

        now = utc_now()
        if action == "publish":
            job.published_at = now
        elif action == "close":
            job.closed_at = now
        elif action == "reopen":
            job.reopened_at = now
        elif action == "request_changes":
            job.change_request_reason = reason_text

        # 7. Record Immutable Lifecycle History
        primary_role = next(iter(normalized_user_roles), "user")
        history_entry = JobLifecycleHistory(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            job_id=job.id,
            previous_status=current_status,
            new_status=target_status,
            action=action,
            actor_id=user_id,
            actor_role=primary_role,
            reason=reason_text,
            audit_metadata=request.audit_metadata,
            created_at=now,
        )
        db.add(history_entry)
        await db.commit()
        await db.refresh(history_entry)

        # 8. Resolve Actor Details for Response
        actor_res = await db.execute(select(User).where(User.id == user_id))
        actor = actor_res.scalar_one_or_none()
        actor_name = f"{actor.first_name} {actor.last_name}".strip() if actor else None
        actor_email = actor.email if actor else None

        # 9. Asynchronously Dispatch Lifecycle Notification via Celery
        try:
            from app.modules.notifications.tasks import (
                dispatch_job_lifecycle_notification,
            )

            recipients: list[dict[str, str]] = []
            if job.recruiter and job.recruiter.email:
                recipients.append({"email": job.recruiter.email, "role": "recruiter"})
            if job.hiring_manager and job.hiring_manager.email:
                recipients.append({"email": job.hiring_manager.email, "role": "hiring_manager"})

            dispatch_job_lifecycle_notification.delay(
                job_id=str(job.id),
                tenant_id=str(tenant_id),
                action=action,
                previous_status=current_status,
                new_status=target_status,
                actor_id=str(user_id),
                actor_name=actor_name,
                recipients=recipients,
                reason=reason_text,
                idempotency_key=f"job-lifecycle-{job.id}-{action}-{int(now.timestamp())}",
            )
        except Exception as exc:
            logger.warning("Could not enqueue Celery job lifecycle notification: %s", exc)

        # 10. Compute Permitted Next Actions
        next_rules = TRANSITION_RULES.get(target_status, {})
        permitted_next = list(next_rules.keys())

        # 11. Format Responses
        updated_read = await hr_requisition_service.get_requisition(db, tenant_id, job.id)
        if not updated_read:
            raise AppException(message="Failed to retrieve updated requisition", status_code=500)

        history_item = JobLifecycleHistoryItem(
            id=history_entry.id,
            job_id=history_entry.job_id,
            previous_status=history_entry.previous_status,
            new_status=history_entry.new_status,
            action=history_entry.action,
            actor_id=history_entry.actor_id,
            actor_name=actor_name,
            actor_email=actor_email,
            actor_role=history_entry.actor_role,
            reason=history_entry.reason,
            audit_metadata=history_entry.audit_metadata,
            created_at=history_entry.created_at,
        )

        return JobLifecycleTransitionResponse(
            job=updated_read,
            transition=history_item,
            permitted_next_actions=permitted_next,
        )

    async def get_history(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
    ) -> list[JobLifecycleHistoryItem]:
        """Retrieve the immutable audit history of lifecycle state transitions for a requisition."""
        # Verify job belongs to tenant
        job_check = await db.execute(
            select(Job.id).where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        if not job_check.scalar_one_or_none():
            raise EntityNotFoundException("JobRequisition", job_id)

        stmt = (
            select(JobLifecycleHistory, User)
            .outerjoin(User, User.id == JobLifecycleHistory.actor_id)
            .where(
                JobLifecycleHistory.job_id == job_id,
                JobLifecycleHistory.tenant_id == tenant_id,
            )
            .order_by(JobLifecycleHistory.created_at.desc())
        )
        results = await db.execute(stmt)
        items: list[JobLifecycleHistoryItem] = []
        for hist, user in results.all():
            actor_name = f"{user.first_name} {user.last_name}".strip() if user else None
            actor_email = user.email if user else None
            items.append(
                JobLifecycleHistoryItem(
                    id=hist.id,
                    job_id=hist.job_id,
                    previous_status=hist.previous_status,
                    new_status=hist.new_status,
                    action=hist.action,
                    actor_id=hist.actor_id,
                    actor_name=actor_name,
                    actor_email=actor_email,
                    actor_role=hist.actor_role,
                    reason=hist.reason,
                    audit_metadata=hist.audit_metadata,
                    created_at=hist.created_at,
                )
            )
        return items

    async def evaluate_permitted_actions(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
        user_id: UUID,
        user_roles: list[str],
        is_super_admin: bool = False,
    ) -> JobLifecyclePermittedActionsResponse:
        """Evaluate which lifecycle transitions the calling user is authorized to perform."""
        stmt = (
            select(Job)
            .where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("JobRequisition", job_id)

        current_status = job.status
        transitions = TRANSITION_RULES.get(current_status, {})
        normalized_roles = {r.lower() for r in user_roles}

        permitted: list[str] = []
        can_approve = False
        separation_of_duties_active = False

        for action_name, rule in transitions.items():
            allowed = rule["allowed_roles"]
            if normalized_roles.intersection(allowed) or is_super_admin:
                if rule.get("enforce_separation_of_duties"):
                    if job.recruiter_id and user_id == job.recruiter_id and not is_super_admin:
                        separation_of_duties_active = True
                        continue  # Cannot approve own requisition
                    can_approve = True
                permitted.append(action_name)

        return JobLifecyclePermittedActionsResponse(
            job_id=job.id,
            current_status=job.status,
            approval_status=job.approval_status,
            permitted_actions=permitted,
            can_approve=can_approve,
            separation_of_duties_active=separation_of_duties_active,
        )


hr_job_lifecycle_service = HrJobLifecycleService()
