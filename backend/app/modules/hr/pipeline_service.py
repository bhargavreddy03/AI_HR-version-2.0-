"""Recruitment Pipeline and Application Stage Management Service.

Enforces Finite State Machine (FSM) rules, optimistic locking, immutable stage history,
strict role-based transition controls, and safe candidate-facing status mapping.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AppException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
)
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.candidates.models import CandidateResume
from app.modules.hr.pipeline_schemas import (
    ApplicationStageHistoryItem,
    BulkStageMoveResponse,
    BulkStageMoveSkippedItem,
    PipelineBoardResponse,
    PipelineCardItem,
    PipelineStageColumn,
    PipelineStageConfig,
    StageTransitionResponse,
)
from app.modules.jobs.models import (
    ApplicationStageHistory,
    CandidateFacingStatus,
    Job,
    JobApplication,
)
from app.modules.organizations.models import Organization

logger = logging.getLogger(__name__)

# Standard recruitment workflow stages in order
DEFAULT_PIPELINE_STAGES = [
    {"id": "applied", "label": "Applied", "order": 1, "is_terminal": False},
    {"id": "resume_review", "label": "Resume Review", "order": 2, "is_terminal": False},
    {"id": "screening", "label": "Screening", "order": 3, "is_terminal": False},
    {"id": "shortlisted", "label": "Shortlisted", "order": 4, "is_terminal": False},
    {"id": "assessment", "label": "Assessment", "order": 5, "is_terminal": False},
    {"id": "interview", "label": "Interview", "order": 6, "is_terminal": False},
    {"id": "final_interview", "label": "Final Interview", "order": 7, "is_terminal": False},
    {"id": "offer", "label": "Offer", "order": 8, "is_terminal": False},
    {"id": "hired", "label": "Hired", "order": 9, "is_terminal": True},
    {"id": "rejected", "label": "Rejected", "order": 10, "is_terminal": True},
    {"id": "withdrawn", "label": "Withdrawn", "order": 11, "is_terminal": True},
]

# Normalization map for legacy and alternate status names
STATUS_NORMALIZATION: dict[str, str] = {
    "submitted": "applied",
    "in_screening": "screening",
    "under_review": "resume_review",
    "review": "resume_review",
    "interviewing": "interview",
    "interview_stage": "interview",
    "offer_stage": "offer",
    "not_selected": "rejected",
}

# FSM stage transition rules
PIPELINE_TRANSITION_RULES: dict[str, set[str]] = {
    "applied": {"resume_review", "screening", "rejected", "withdrawn"},
    "resume_review": {"screening", "shortlisted", "rejected", "withdrawn"},
    "screening": {"shortlisted", "assessment", "interview", "rejected", "withdrawn"},
    "shortlisted": {"assessment", "interview", "offer", "rejected", "withdrawn"},
    "assessment": {"interview", "final_interview", "shortlisted", "rejected", "withdrawn"},
    "interview": {"final_interview", "assessment", "offer", "rejected", "withdrawn"},
    "final_interview": {"offer", "interview", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(),  # Terminal state: cannot be moved
    "withdrawn": set(),  # Protected state: candidate initiated withdrawal
    "rejected": {"screening", "resume_review", "shortlisted"},  # Reconsideration with reason
}

# Mapping from internal pipeline stage to candidate-facing portal status
STAGE_TO_CANDIDATE_STATUS: dict[str, str] = {
    "applied": CandidateFacingStatus.SUBMITTED.value,
    "resume_review": CandidateFacingStatus.UNDER_REVIEW.value,
    "screening": CandidateFacingStatus.IN_SCREENING.value,
    "shortlisted": CandidateFacingStatus.IN_SCREENING.value,
    "assessment": CandidateFacingStatus.INTERVIEW_STAGE.value,
    "interview": CandidateFacingStatus.INTERVIEW_STAGE.value,
    "final_interview": CandidateFacingStatus.INTERVIEW_STAGE.value,
    "offer": CandidateFacingStatus.OFFER_STAGE.value,
    "hired": CandidateFacingStatus.OFFER_STAGE.value,
    "rejected": CandidateFacingStatus.NOT_SELECTED.value,
    "withdrawn": CandidateFacingStatus.WITHDRAWN.value,
}


def normalize_stage(stage_str: str) -> str:
    """Normalize stage string to canonical pipeline stage identifier."""
    cleaned = stage_str.strip().lower()
    return STATUS_NORMALIZATION.get(cleaned, cleaned)


class HrPipelineService:
    """Service orchestrating recruitment pipeline Kanban boards, FSM transitions, and stage history."""

    async def get_configured_stages(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[PipelineStageConfig]:
        """Retrieve organization-configured pipeline stages or default workflow."""
        org_res = await db.execute(
            select(Organization.pipeline_stages).where(Organization.id == tenant_id)
        )
        custom_stages = org_res.scalar_one_or_none()
        if custom_stages and isinstance(custom_stages, list) and len(custom_stages) > 0:
            return [PipelineStageConfig.model_validate(s) for s in custom_stages]

        return [PipelineStageConfig.model_validate(s) for s in DEFAULT_PIPELINE_STAGES]

    async def get_pipeline_board(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID | None = None,
        recruiter_id: UUID | None = None,
        search: str | None = None,
        limit_per_stage: int = 25,
    ) -> PipelineBoardResponse:
        """Fetch Kanban-style recruitment pipeline cards grouped by workflow stages."""
        # 1. Resolve organization stages
        stage_configs = await self.get_configured_stages(db, tenant_id)
        stage_ids = [s.id for s in stage_configs]

        # 2. Base filters
        filters = [JobApplication.tenant_id == tenant_id]
        if job_id:
            filters.append(JobApplication.job_id == job_id)
        if recruiter_id:
            filters.append(Job.recruiter_id == recruiter_id)

        candidate_user = User
        query = (
            select(
                JobApplication,
                Job,
                candidate_user,
                CandidateUserProfile,
                CandidateResume,
            )
            .join(Job, Job.id == JobApplication.job_id)
            .join(candidate_user, candidate_user.id == JobApplication.candidate_id)
            .outerjoin(CandidateUserProfile, CandidateUserProfile.user_id == candidate_user.id)
            .outerjoin(CandidateResume, CandidateResume.id == JobApplication.resume_id)
            .options(selectinload(Job.recruiter))
            .where(*filters)
        )

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    candidate_user.first_name.ilike(term),
                    candidate_user.last_name.ilike(term),
                    candidate_user.email.ilike(term),
                    Job.title.ilike(term),
                    CandidateUserProfile.headline.ilike(term),
                )
            )

        query = query.order_by(desc(JobApplication.applied_at))
        rows = (await db.execute(query)).all()

        # 3. Group cards by normalized stage
        cards_by_stage: dict[str, list[PipelineCardItem]] = {s_id: [] for s_id in stage_ids}
        total_candidates = len(rows)

        for app, job, user, profile, resume in rows:
            norm_stage = normalize_stage(app.status)
            if norm_stage not in cards_by_stage:
                norm_stage = "applied"

            # Derive skills
            cand_skills = set(profile.self_declared_skills if profile else [])
            if resume and resume.skills_extracted:
                cand_skills.update(resume.skills_extracted)

            recruiter_name = (
                f"{job.recruiter.first_name} {job.recruiter.last_name}" if job.recruiter else None
            )

            # Last activity
            last_activity = app.updated_at or app.applied_at
            if app.timeline and isinstance(app.timeline, list) and len(app.timeline) > 0:
                last_event = app.timeline[-1]
                if isinstance(last_event, dict) and "changed_at" in last_event:
                    try:
                        last_activity = datetime.fromisoformat(
                            last_event["changed_at"].replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

            card = PipelineCardItem(
                application_id=app.id,
                candidate_id=app.candidate_id,
                candidate_name=f"{user.first_name} {user.last_name}",
                candidate_email=user.email,
                candidate_headline=profile.headline if profile else None,
                candidate_avatar_url=user.avatar_url,
                job_id=job.id,
                job_title=job.title,
                job_department=job.department,
                stage=norm_stage,
                stage_version=getattr(app, "stage_version", 1),
                applied_at=app.applied_at,
                last_activity_at=last_activity,
                recruiter_id=job.recruiter_id,
                recruiter_name=recruiter_name,
                skills=sorted(cand_skills)[:4],
                resume_available=bool(app.resume_id or app.resume_snapshot_sha256),
            )
            cards_by_stage[norm_stage].append(card)

        # 4. Construct columns
        columns: list[PipelineStageColumn] = []
        for config in stage_configs:
            all_stage_cards = cards_by_stage.get(config.id, [])
            columns.append(
                PipelineStageColumn(
                    id=config.id,
                    label=config.label,
                    order=config.order,
                    is_terminal=config.is_terminal,
                    count=len(all_stage_cards),
                    cards=all_stage_cards[:limit_per_stage],
                )
            )

        return PipelineBoardResponse(
            tenant_id=tenant_id,
            stages=columns,
            total_candidates=total_candidates,
            active_filters={
                "job_id": str(job_id) if job_id else None,
                "recruiter_id": str(recruiter_id) if recruiter_id else None,
                "search": search,
            },
        )

    async def transition_stage(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_id: UUID,
        target_stage: str,
        actor_id: UUID,
        actor_role: str,
        actor_name: str,
        reason: str | None = None,
        expected_stage_version: int | None = None,
        notes: str | None = None,
    ) -> StageTransitionResponse:
        """Validate and execute a single recruitment pipeline stage transition."""
        norm_target = normalize_stage(target_stage)

        # 1. Fetch application scoped strictly to tenant
        app_res = await db.execute(
            select(JobApplication).where(
                JobApplication.id == application_id,
                JobApplication.tenant_id == tenant_id,
            )
        )
        app = app_res.scalar_one_or_none()
        if not app:
            raise EntityNotFoundException("JobApplication", application_id)

        current_norm = normalize_stage(app.status)

        # 2. Optimistic Concurrency Control
        if expected_stage_version is not None and app.stage_version != expected_stage_version:
            raise ConflictException(
                message=(
                    f"Concurrent update conflict: the application was modified by another user "
                    f"(expected version {expected_stage_version}, current {app.stage_version}). "
                    f"Please refresh and retry."
                ),
                error_code="CONCURRENT_UPDATE_CONFLICT",
            )

        # 3. Protected / Terminal State Safeguards
        if current_norm == "withdrawn":
            raise ConflictException(
                message="Cannot modify stage: candidate has withdrawn their application.",
                error_code="APPLICATION_WITHDRAWN",
            )
        if current_norm == "hired":
            raise ConflictException(
                message="Cannot modify stage: candidate has already been hired.",
                error_code="APPLICATION_HIRED_TERMINAL",
            )
        if current_norm == norm_target:
            raise ConflictException(
                message=f"Application is already in stage '{norm_target}'.",
                error_code="SAME_STAGE_TRANSITION",
            )

        # 4. Mandatory Rejection Reason Rule
        if norm_target == "rejected":
            if not reason or not reason.strip():
                raise AppException(
                    message="A specific rejection reason is mandatory when moving a candidate to rejected stage.",
                    status_code=400,
                    code="REJECTION_REASON_REQUIRED",
                )

        # 5. Role Authority Checks for Sensitive Stages (Offer / Hired)
        authorized_hire_roles = {"hiring_manager", "org_admin", "admin", "platform_super_admin"}
        if norm_target in ("offer", "hired") and actor_role not in authorized_hire_roles:
            raise AuthorizationException(
                message="Only designated hiring managers or organization administrators can extend offers or hire candidates.",
                error_code="INSUFFICIENT_STAGE_PERMISSIONS",
            )

        # 6. FSM Transition Graph Verification
        allowed_transitions = PIPELINE_TRANSITION_RULES.get(current_norm, set())
        if norm_target not in allowed_transitions:
            raise ConflictException(
                message=f"Invalid recruitment stage transition from '{current_norm}' to '{norm_target}'.",
                error_code="INVALID_STAGE_TRANSITION",
            )

        # 7. Update Application State
        previous_stage = app.status
        now = utc_now()
        app.status = norm_target
        app.candidate_status = STAGE_TO_CANDIDATE_STATUS.get(
            norm_target, CandidateFacingStatus.UNDER_REVIEW.value
        )
        app.stage_version = (app.stage_version or 1) + 1
        if norm_target == "rejected" and reason:
            app.rejection_reason = reason.strip()

        # 8. Insert Immutable Stage History
        history_entry = ApplicationStageHistory(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            application_id=app.id,
            previous_stage=previous_stage,
            new_stage=norm_target,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason.strip() if reason else None,
            audit_metadata={"notes": notes} if notes else {},
            created_at=now,
        )
        db.add(history_entry)

        # 9. Update Timeline Entry
        current_timeline = list(app.timeline or [])
        is_internal = norm_target not in ("applied", "interview", "offer", "rejected")
        timeline_entry = {
            "status": norm_target,
            "changed_at": now.isoformat(),
            "note": reason or f"Stage changed to {norm_target}",
            "actor_name": actor_name,
            "actor_role": actor_role,
            "is_internal": is_internal,
        }
        current_timeline.append(timeline_entry)
        app.timeline = current_timeline

        await db.commit()

        return StageTransitionResponse(
            application_id=app.id,
            previous_stage=previous_stage,
            new_stage=norm_target,
            stage_version=app.stage_version,
            candidate_status=app.candidate_status,
            changed_at=now,
            actor_name=actor_name,
            actor_role=actor_role,
            reason=reason,
        )

    async def bulk_stage_move(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_ids: list[UUID],
        target_stage: str,
        actor_id: UUID,
        actor_role: str,
        actor_name: str,
        reason: str | None = None,
    ) -> BulkStageMoveResponse:
        """Move multiple applications to a new stage while strictly evaluating transition rules per application."""
        norm_target = normalize_stage(target_stage)

        # Mandatory rejection reason check
        if norm_target == "rejected" and (not reason or not reason.strip()):
            raise AppException(
                message="A rejection reason is required for bulk candidate rejection.",
                status_code=400,
                code="REJECTION_REASON_REQUIRED",
            )

        # Role authority check for sensitive stages
        authorized_hire_roles = {"hiring_manager", "org_admin", "admin", "platform_super_admin"}
        if norm_target in ("offer", "hired") and actor_role not in authorized_hire_roles:
            raise AuthorizationException(
                message="Only designated hiring managers or organization administrators can extend offers or hire candidates.",
                error_code="INSUFFICIENT_STAGE_PERMISSIONS",
            )

        # Query all specified applications strictly under this tenant
        candidate_user = User
        stmt = (
            select(JobApplication, candidate_user)
            .join(candidate_user, candidate_user.id == JobApplication.candidate_id)
            .where(
                JobApplication.id.in_(application_ids),
                JobApplication.tenant_id == tenant_id,
            )
        )
        rows = (await db.execute(stmt)).all()
        found_app_ids = {r[0].id for r in rows}

        updated_ids: list[UUID] = []
        skipped: list[BulkStageMoveSkippedItem] = []
        now = utc_now()

        # Handle any application IDs not found in tenant
        for req_id in application_ids:
            if req_id not in found_app_ids:
                skipped.append(
                    BulkStageMoveSkippedItem(
                        application_id=req_id,
                        candidate_name="Unknown",
                        current_stage="unknown",
                        reason="Application not found under this organization",
                    )
                )

        for app, user in rows:
            cand_name = f"{user.first_name} {user.last_name}"
            current_norm = normalize_stage(app.status)

            # Evaluate eligibility against rules
            if current_norm == "withdrawn":
                skipped.append(
                    BulkStageMoveSkippedItem(
                        application_id=app.id,
                        candidate_name=cand_name,
                        current_stage=current_norm,
                        reason="Candidate has withdrawn their application",
                    )
                )
                continue

            if current_norm == "hired":
                skipped.append(
                    BulkStageMoveSkippedItem(
                        application_id=app.id,
                        candidate_name=cand_name,
                        current_stage=current_norm,
                        reason="Candidate is already in terminal hired stage",
                    )
                )
                continue

            if current_norm == norm_target:
                skipped.append(
                    BulkStageMoveSkippedItem(
                        application_id=app.id,
                        candidate_name=cand_name,
                        current_stage=current_norm,
                        reason=f"Application is already in '{norm_target}' stage",
                    )
                )
                continue

            allowed = PIPELINE_TRANSITION_RULES.get(current_norm, set())
            if norm_target not in allowed:
                skipped.append(
                    BulkStageMoveSkippedItem(
                        application_id=app.id,
                        candidate_name=cand_name,
                        current_stage=current_norm,
                        reason=f"Transition from '{current_norm}' to '{norm_target}' is prohibited by workflow rules",
                    )
                )
                continue

            # Valid transition: apply state changes
            previous_stage = app.status
            app.status = norm_target
            app.candidate_status = STAGE_TO_CANDIDATE_STATUS.get(
                norm_target, CandidateFacingStatus.UNDER_REVIEW.value
            )
            app.stage_version = (app.stage_version or 1) + 1
            if norm_target == "rejected" and reason:
                app.rejection_reason = reason.strip()

            # Stage history
            history_entry = ApplicationStageHistory(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                application_id=app.id,
                previous_stage=previous_stage,
                new_stage=norm_target,
                actor_id=actor_id,
                actor_role=actor_role,
                reason=reason.strip() if reason else None,
                audit_metadata={"bulk_operation": True},
                created_at=now,
            )
            db.add(history_entry)

            # Timeline
            current_timeline = list(app.timeline or [])
            current_timeline.append(
                {
                    "status": norm_target,
                    "changed_at": now.isoformat(),
                    "note": reason or f"Bulk transition to {norm_target}",
                    "actor_name": actor_name,
                    "actor_role": actor_role,
                    "is_internal": norm_target not in ("applied", "interview", "offer", "rejected"),
                }
            )
            app.timeline = current_timeline
            updated_ids.append(app.id)

        if updated_ids:
            await db.commit()

        return BulkStageMoveResponse(
            target_stage=norm_target,
            total_requested=len(application_ids),
            updated_count=len(updated_ids),
            updated_ids=updated_ids,
            skipped_count=len(skipped),
            skipped=skipped,
        )

    async def get_stage_history(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_id: UUID,
    ) -> list[ApplicationStageHistoryItem]:
        """Retrieve chronological immutable audit history of stage transitions for an application."""
        # Tenant boundary check
        app_res = await db.execute(
            select(JobApplication.id).where(
                JobApplication.id == application_id,
                JobApplication.tenant_id == tenant_id,
            )
        )
        if not app_res.scalar_one_or_none():
            raise EntityNotFoundException("JobApplication", application_id)

        user_alias = User
        stmt = (
            select(ApplicationStageHistory, user_alias)
            .outerjoin(user_alias, user_alias.id == ApplicationStageHistory.actor_id)
            .where(
                ApplicationStageHistory.application_id == application_id,
                ApplicationStageHistory.tenant_id == tenant_id,
            )
            .order_by(desc(ApplicationStageHistory.created_at))
        )
        rows = (await db.execute(stmt)).all()

        items: list[ApplicationStageHistoryItem] = []
        for hist, actor in rows:
            actor_name = f"{actor.first_name} {actor.last_name}" if actor else "System"
            items.append(
                ApplicationStageHistoryItem(
                    id=hist.id,
                    application_id=hist.application_id,
                    previous_stage=hist.previous_stage,
                    new_stage=hist.new_stage,
                    actor_id=hist.actor_id,
                    actor_name=actor_name,
                    actor_role=hist.actor_role,
                    reason=hist.reason,
                    audit_metadata=hist.audit_metadata or {},
                    created_at=hist.created_at,
                )
            )
        return items


hr_pipeline_service = HrPipelineService()
