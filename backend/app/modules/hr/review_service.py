"""Service for candidate review workspace, internal notes, scorecards, tasks, and unified timeline.

Enforces strict tenant isolation, note authorship rules, confidentiality controls,
and separate internal vs candidate-visible activity event logging.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AuthorizationException,
    EntityNotFoundException,
    ValidationException,
)
from app.modules.auth.models import User
from app.modules.hr.review_schemas import (
    CandidateActivityTimelineResponse,
    CandidateTimelineItem,
    CreateInternalNoteRequest,
    CreateRecruitmentTaskRequest,
    InternalNoteResponse,
    RecruitmentTaskResponse,
    ReviewFeedbackResponse,
    SubmitReviewFeedbackRequest,
    UpdateInternalNoteRequest,
    UpdateRecruitmentTaskRequest,
)
from app.modules.jobs.models import (
    ApplicationStageHistory,
    CandidateInternalNote,
    CandidateRecruitmentTask,
    CandidateReviewFeedback,
    Job,
    JobApplication,
    JobAssignmentHistory,
)
from app.modules.organizations.models import OrganizationMembership

logger = logging.getLogger(__name__)


class HrReviewService:
    """Service managing internal HR collaboration, scorecards, notes, tasks, and activity timelines."""

    async def _verify_candidate_belongs_to_tenant(
        self, db: AsyncSession, tenant_id: UUID, candidate_id: UUID
    ) -> None:
        """Verify candidate has submitted at least one application to this tenant organization."""
        stmt = (
            select(JobApplication.id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.tenant_id == tenant_id,
            )
            .limit(1)
        )
        res = await db.execute(stmt)
        if not res.scalar_one_or_none():
            raise AuthorizationException(
                "Candidate profile is not accessible to this organization.",
                code="CANDIDATE_ACCESS_FORBIDDEN",
            )

    # ------------------------------------------------------------------
    # Internal Notes Management
    # ------------------------------------------------------------------

    async def add_internal_note(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID,
        author_id: UUID,
        author_name: str,
        author_role: str,
        request: CreateInternalNoteRequest,
    ) -> InternalNoteResponse:
        """Add an internal note to a candidate profile, optionally scoped to an application."""
        await self._verify_candidate_belongs_to_tenant(db, tenant_id, candidate_id)

        if request.application_id:
            app = await db.get(JobApplication, request.application_id)
            if not app or app.tenant_id != tenant_id or app.candidate_id != candidate_id:
                raise EntityNotFoundException("Job Application", request.application_id)

        note = CandidateInternalNote(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            application_id=request.application_id,
            author_id=author_id,
            author_name=author_name,
            author_role=author_role,
            content=request.content.strip(),
            category=request.category,
            is_confidential=request.is_confidential,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(note)
        await db.commit()

        return InternalNoteResponse(
            id=note.id,
            candidate_id=note.candidate_id,
            application_id=note.application_id,
            author_id=note.author_id,
            author_name=note.author_name,
            author_role=note.author_role,
            content=note.content,
            category=note.category,
            is_confidential=note.is_confidential,
            can_edit=True,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    async def get_internal_notes(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID,
        actor_id: UUID,
        is_admin: bool = False,
        application_id: UUID | None = None,
    ) -> list[InternalNoteResponse]:
        """Fetch internal notes for candidate respecting confidentiality permissions."""
        await self._verify_candidate_belongs_to_tenant(db, tenant_id, candidate_id)

        conditions = [
            CandidateInternalNote.tenant_id == tenant_id,
            CandidateInternalNote.candidate_id == candidate_id,
        ]
        if application_id:
            conditions.append(
                or_(
                    CandidateInternalNote.application_id == application_id,
                    CandidateInternalNote.application_id.is_(None),
                )
            )

        stmt = select(CandidateInternalNote).where(*conditions).order_by(desc(CandidateInternalNote.created_at))
        res = await db.execute(stmt)
        notes = res.scalars().all()

        results: list[InternalNoteResponse] = []
        for n in notes:
            # Confidential notes can only be viewed by the author or organization admins
            if n.is_confidential and not (is_admin or n.author_id == actor_id):
                continue

            can_edit = is_admin or (n.author_id == actor_id)
            results.append(
                InternalNoteResponse(
                    id=n.id,
                    candidate_id=n.candidate_id,
                    application_id=n.application_id,
                    author_id=n.author_id,
                    author_name=n.author_name,
                    author_role=n.author_role,
                    content=n.content,
                    category=n.category,
                    is_confidential=n.is_confidential,
                    can_edit=can_edit,
                    created_at=n.created_at,
                    updated_at=n.updated_at,
                )
            )

        return results

    async def update_internal_note(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        note_id: UUID,
        actor_id: UUID,
        is_admin: bool,
        request: UpdateInternalNoteRequest,
    ) -> InternalNoteResponse:
        """Update an existing internal note (restricted to author or org admin)."""
        note = await db.get(CandidateInternalNote, note_id)
        if not note or note.tenant_id != tenant_id:
            raise EntityNotFoundException("Internal Note", note_id)

        if not (is_admin or note.author_id == actor_id):
            raise AuthorizationException(
                "You can only edit notes you personally authored.",
                code="NOTE_EDIT_FORBIDDEN",
            )

        note.content = request.content.strip()
        if request.category is not None:
            note.category = request.category
        if request.is_confidential is not None:
            note.is_confidential = request.is_confidential
        note.updated_at = utc_now()

        await db.commit()

        return InternalNoteResponse(
            id=note.id,
            candidate_id=note.candidate_id,
            application_id=note.application_id,
            author_id=note.author_id,
            author_name=note.author_name,
            author_role=note.author_role,
            content=note.content,
            category=note.category,
            is_confidential=note.is_confidential,
            can_edit=True,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    async def delete_internal_note(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        note_id: UUID,
        actor_id: UUID,
        is_admin: bool,
    ) -> None:
        """Delete an internal note (restricted to author or org admin)."""
        note = await db.get(CandidateInternalNote, note_id)
        if not note or note.tenant_id != tenant_id:
            raise EntityNotFoundException("Internal Note", note_id)

        if not (is_admin or note.author_id == actor_id):
            raise AuthorizationException(
                "You can only delete notes you personally authored.",
                code="NOTE_DELETE_FORBIDDEN",
            )

        await db.delete(note)
        await db.commit()

    # ------------------------------------------------------------------
    # Review Scorecard Feedback Management
    # ------------------------------------------------------------------

    async def submit_review_feedback(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_id: UUID,
        reviewer_id: UUID,
        reviewer_name: str,
        reviewer_role: str,
        request: SubmitReviewFeedbackRequest,
    ) -> ReviewFeedbackResponse:
        """Submit or update structured evaluation feedback / scorecard for an application."""
        app = await db.get(JobApplication, application_id)
        if not app or app.tenant_id != tenant_id:
            raise EntityNotFoundException("Job Application", application_id)

        valid_recommendations = {"strong_yes", "yes", "neutral", "no", "strong_no"}
        if request.recommendation not in valid_recommendations:
            raise ValidationException(
                f"Invalid recommendation '{request.recommendation}'. Must be one of {valid_recommendations}.",
                code="INVALID_RECOMMENDATION",
            )

        # Check if reviewer already submitted review for this application
        stmt = select(CandidateReviewFeedback).where(
            CandidateReviewFeedback.tenant_id == tenant_id,
            CandidateReviewFeedback.application_id == application_id,
            CandidateReviewFeedback.reviewer_id == reviewer_id,
        )
        res = await db.execute(stmt)
        feedback = res.scalar_one_or_none()

        if feedback:
            feedback.recommendation = request.recommendation
            feedback.technical_rating = request.technical_rating
            feedback.communication_rating = request.communication_rating
            feedback.cultural_rating = request.cultural_rating
            feedback.overall_rating = request.overall_rating
            feedback.summary = request.summary.strip()
            feedback.pros = request.pros
            feedback.cons = request.cons
            feedback.updated_at = utc_now()
        else:
            feedback = CandidateReviewFeedback(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                application_id=application_id,
                reviewer_id=reviewer_id,
                reviewer_name=reviewer_name,
                reviewer_role=reviewer_role,
                recommendation=request.recommendation,
                technical_rating=request.technical_rating,
                communication_rating=request.communication_rating,
                cultural_rating=request.cultural_rating,
                overall_rating=request.overall_rating,
                summary=request.summary.strip(),
                pros=request.pros,
                cons=request.cons,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(feedback)

        await db.commit()

        return ReviewFeedbackResponse(
            id=feedback.id,
            application_id=feedback.application_id,
            reviewer_id=feedback.reviewer_id,
            reviewer_name=feedback.reviewer_name,
            reviewer_role=feedback.reviewer_role,
            recommendation=feedback.recommendation,
            technical_rating=feedback.technical_rating,
            communication_rating=feedback.communication_rating,
            cultural_rating=feedback.cultural_rating,
            overall_rating=feedback.overall_rating,
            summary=feedback.summary,
            pros=feedback.pros or [],
            cons=feedback.cons or [],
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )

    async def get_application_reviews(
        self, db: AsyncSession, tenant_id: UUID, application_id: UUID
    ) -> list[ReviewFeedbackResponse]:
        """Fetch all evaluation scorecards submitted for an application."""
        app = await db.get(JobApplication, application_id)
        if not app or app.tenant_id != tenant_id:
            raise EntityNotFoundException("Job Application", application_id)

        stmt = (
            select(CandidateReviewFeedback)
            .where(
                CandidateReviewFeedback.tenant_id == tenant_id,
                CandidateReviewFeedback.application_id == application_id,
            )
            .order_by(desc(CandidateReviewFeedback.created_at))
        )
        res = await db.execute(stmt)
        feedbacks = res.scalars().all()

        return [
            ReviewFeedbackResponse(
                id=fb.id,
                application_id=fb.application_id,
                reviewer_id=fb.reviewer_id,
                reviewer_name=fb.reviewer_name,
                reviewer_role=fb.reviewer_role,
                recommendation=fb.recommendation,
                technical_rating=fb.technical_rating,
                communication_rating=fb.communication_rating,
                cultural_rating=fb.cultural_rating,
                overall_rating=fb.overall_rating,
                summary=fb.summary,
                pros=fb.pros or [],
                cons=fb.cons or [],
                created_at=fb.created_at,
                updated_at=fb.updated_at,
            )
            for fb in feedbacks
        ]

    # ------------------------------------------------------------------
    # Recruitment Tasks & Follow-ups Management
    # ------------------------------------------------------------------

    async def create_task(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID,
        creator_id: UUID,
        creator_name: str,
        request: CreateRecruitmentTaskRequest,
    ) -> RecruitmentTaskResponse:
        """Create a recruitment follow-up task for a candidate application."""
        await self._verify_candidate_belongs_to_tenant(db, tenant_id, candidate_id)

        assignee_name = None
        if request.assignee_id:
            # Validate assignee is an active organization member
            stmt = (
                select(User)
                .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == request.assignee_id,
                    OrganizationMembership.is_active.is_(True),
                )
            )
            res = await db.execute(stmt)
            assignee = res.scalar_one_or_none()
            if not assignee:
                raise ValidationException(
                    "Assignee is not an active member of this organization.",
                    code="USER_NOT_ORGANIZATION_MEMBER",
                )
            assignee_name = f"{assignee.first_name} {assignee.last_name}".strip()

        task = CandidateRecruitmentTask(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            application_id=request.application_id,
            creator_id=creator_id,
            creator_name=creator_name,
            assignee_id=request.assignee_id,
            assignee_name=assignee_name,
            title=request.title.strip(),
            description=request.description.strip() if request.description else None,
            task_type=request.task_type,
            due_date=request.due_date,
            is_completed=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(task)
        await db.commit()

        return RecruitmentTaskResponse(
            id=task.id,
            candidate_id=task.candidate_id,
            application_id=task.application_id,
            creator_id=task.creator_id,
            creator_name=task.creator_name,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            due_date=task.due_date,
            is_completed=task.is_completed,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def get_tasks(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID | None = None,
        application_id: UUID | None = None,
        assignee_id: UUID | None = None,
        is_completed: bool | None = None,
    ) -> list[RecruitmentTaskResponse]:
        """Fetch recruitment follow-up tasks with flexible filters."""
        conditions = [CandidateRecruitmentTask.tenant_id == tenant_id]
        if candidate_id:
            conditions.append(CandidateRecruitmentTask.candidate_id == candidate_id)
        if application_id:
            conditions.append(CandidateRecruitmentTask.application_id == application_id)
        if assignee_id:
            conditions.append(CandidateRecruitmentTask.assignee_id == assignee_id)
        if is_completed is not None:
            conditions.append(CandidateRecruitmentTask.is_completed == is_completed)

        stmt = select(CandidateRecruitmentTask).where(*conditions).order_by(
            CandidateRecruitmentTask.is_completed.asc(),
            CandidateRecruitmentTask.due_date.asc().nulls_last(),
            desc(CandidateRecruitmentTask.created_at),
        )
        res = await db.execute(stmt)
        tasks = res.scalars().all()

        return [
            RecruitmentTaskResponse(
                id=t.id,
                candidate_id=t.candidate_id,
                application_id=t.application_id,
                creator_id=t.creator_id,
                creator_name=t.creator_name,
                assignee_id=t.assignee_id,
                assignee_name=t.assignee_name,
                title=t.title,
                description=t.description,
                task_type=t.task_type,
                due_date=t.due_date,
                is_completed=t.is_completed,
                completed_at=t.completed_at,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tasks
        ]

    async def update_task(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        task_id: UUID,
        actor_id: UUID,
        request: UpdateRecruitmentTaskRequest,
    ) -> RecruitmentTaskResponse:
        """Update or mark completed a recruitment task."""
        task = await db.get(CandidateRecruitmentTask, task_id)
        if not task or task.tenant_id != tenant_id:
            raise EntityNotFoundException("Recruitment Task", task_id)

        if request.is_completed is not None:
            task.is_completed = request.is_completed
            if request.is_completed:
                task.completed_at = utc_now()
                task.completed_by_id = actor_id
            else:
                task.completed_at = None
                task.completed_by_id = None

        if request.title is not None:
            task.title = request.title.strip()
        if request.description is not None:
            task.description = request.description.strip() if request.description else None
        if request.due_date is not None:
            task.due_date = request.due_date

        if request.assignee_id is not None:
            stmt = (
                select(User)
                .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == request.assignee_id,
                    OrganizationMembership.is_active.is_(True),
                )
            )
            res = await db.execute(stmt)
            assignee = res.scalar_one_or_none()
            if assignee:
                task.assignee_id = assignee.id
                task.assignee_name = f"{assignee.first_name} {assignee.last_name}".strip()

        task.updated_at = utc_now()
        await db.commit()

        return RecruitmentTaskResponse(
            id=task.id,
            candidate_id=task.candidate_id,
            application_id=task.application_id,
            creator_id=task.creator_id,
            creator_name=task.creator_name,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            due_date=task.due_date,
            is_completed=task.is_completed,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    # ------------------------------------------------------------------
    # Unified Candidate Activity Timeline
    # ------------------------------------------------------------------

    async def get_candidate_timeline(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID,
        application_id: UUID | None = None,
        is_internal_viewer: bool = True,
    ) -> CandidateActivityTimelineResponse:
        """Assemble unified chronological activity history, separating internal from candidate events."""
        await self._verify_candidate_belongs_to_tenant(db, tenant_id, candidate_id)

        events: list[CandidateTimelineItem] = []

        # 1. Fetch applications for candidate in this tenant
        app_stmt = select(JobApplication, Job).join(Job, Job.id == JobApplication.job_id).where(
            JobApplication.candidate_id == candidate_id,
            JobApplication.tenant_id == tenant_id,
        )
        if application_id:
            app_stmt = app_stmt.where(JobApplication.id == application_id)

        apps_res = await db.execute(app_stmt)
        apps_data = apps_res.all()

        app_ids = [app.id for app, _ in apps_data]
        job_ids = list({job.id for _, job in apps_data})

        for app, job in apps_data:
            # Event: Application Submitted (Candidate Visible)
            events.append(
                CandidateTimelineItem(
                    id=f"app-submitted-{app.id}",
                    event_type="application_submitted",
                    title="Application Submitted",
                    description=f"Submitted application for {job.title} ({job.department})",
                    actor_name="Candidate",
                    actor_role="candidate",
                    is_internal=False,
                    timestamp=app.applied_at,
                    metadata={"application_id": str(app.id), "job_title": job.title},
                )
            )

            if app.withdrawn_at:
                events.append(
                    CandidateTimelineItem(
                        id=f"app-withdrawn-{app.id}",
                        event_type="application_withdrawn",
                        title="Application Withdrawn",
                        description=f"Candidate withdrew application: {app.withdrawal_reason or 'No reason provided'}",
                        actor_name="Candidate",
                        actor_role="candidate",
                        is_internal=False,
                        timestamp=app.withdrawn_at,
                        metadata={"application_id": str(app.id)},
                    )
                )

        if app_ids:
            # 2. Stage history transitions
            stage_hist_stmt = (
                select(ApplicationStageHistory)
                .where(
                    ApplicationStageHistory.tenant_id == tenant_id,
                    ApplicationStageHistory.application_id.in_(app_ids),
                )
                .order_by(desc(ApplicationStageHistory.created_at))
            )
            sh_res = await db.execute(stage_hist_stmt)
            for sh in sh_res.scalars().all():
                actor_display = None
                if getattr(sh, "actor", None):
                    actor_display = f"{sh.actor.first_name} {sh.actor.last_name}".strip()
                elif getattr(sh, "actor_role", None):
                    actor_display = sh.actor_role.replace("_", " ").title()

                events.append(
                    CandidateTimelineItem(
                        id=f"stage-move-{sh.id}",
                        event_type="stage_transition",
                        title=f"Stage Advanced to {sh.new_stage.replace('_', ' ').title()}",
                        description=f"Moved from {sh.previous_stage.replace('_', ' ').title()} to {sh.new_stage.replace('_', ' ').title()}"
                        + (f". Reason: {sh.reason}" if sh.reason else ""),
                        actor_name=actor_display,
                        actor_role=sh.actor_role,
                        is_internal=False,
                        timestamp=sh.created_at,
                        metadata={
                            "previous_stage": sh.previous_stage,
                            "new_stage": sh.new_stage,
                            "reason": sh.reason,
                        },
                    )
                )

            # 3. Internal Notes (Only if internal viewer)
            if is_internal_viewer:
                notes_stmt = (
                    select(CandidateInternalNote)
                    .where(
                        CandidateInternalNote.tenant_id == tenant_id,
                        CandidateInternalNote.candidate_id == candidate_id,
                    )
                    .order_by(desc(CandidateInternalNote.created_at))
                )
                n_res = await db.execute(notes_stmt)
                for n in n_res.scalars().all():
                    events.append(
                        CandidateTimelineItem(
                            id=f"note-{n.id}",
                            event_type="note_added",
                            title=f"Internal Note Added ({n.category.title()})",
                            description=n.content[:200] + ("..." if len(n.content) > 200 else ""),
                            actor_name=n.author_name,
                            actor_role=n.author_role,
                            is_internal=True,
                            timestamp=n.created_at,
                            metadata={"category": n.category, "is_confidential": n.is_confidential},
                        )
                    )

                # 4. Review Scorecards (Internal only)
                reviews_stmt = (
                    select(CandidateReviewFeedback)
                    .where(
                        CandidateReviewFeedback.tenant_id == tenant_id,
                        CandidateReviewFeedback.application_id.in_(app_ids),
                    )
                    .order_by(desc(CandidateReviewFeedback.created_at))
                )
                rev_res = await db.execute(reviews_stmt)
                for rev in rev_res.scalars().all():
                    events.append(
                        CandidateTimelineItem(
                            id=f"review-{rev.id}",
                            event_type="review_submitted",
                            title=f"Evaluation Submitted: {rev.recommendation.replace('_', ' ').title()}",
                            description=rev.summary[:200] + ("..." if len(rev.summary) > 200 else ""),
                            actor_name=rev.reviewer_name,
                            actor_role=rev.reviewer_role,
                            is_internal=True,
                            timestamp=rev.created_at,
                            metadata={"recommendation": rev.recommendation, "overall_rating": rev.overall_rating},
                        )
                    )

                # 5. Recruitment Tasks (Internal only)
                tasks_stmt = (
                    select(CandidateRecruitmentTask)
                    .where(
                        CandidateRecruitmentTask.tenant_id == tenant_id,
                        CandidateRecruitmentTask.candidate_id == candidate_id,
                    )
                    .order_by(desc(CandidateRecruitmentTask.created_at))
                )
                task_res = await db.execute(tasks_stmt)
                for t in task_res.scalars().all():
                    events.append(
                        CandidateTimelineItem(
                            id=f"task-{t.id}",
                            event_type="task_completed" if t.is_completed else "task_created",
                            title=f"Task {'Completed' if t.is_completed else 'Created'}: {t.title}",
                            description=t.description,
                            actor_name=t.creator_name,
                            actor_role="recruiter",
                            is_internal=True,
                            timestamp=t.completed_at if t.is_completed and t.completed_at else t.created_at,
                            metadata={"task_type": t.task_type, "is_completed": t.is_completed},
                        )
                    )

        # 6. Job Assignment Changes (Lead Recruiter / Hiring Manager assigned)
        if job_ids and is_internal_viewer:
            job_assign_stmt = (
                select(JobAssignmentHistory)
                .where(
                    JobAssignmentHistory.tenant_id == tenant_id,
                    JobAssignmentHistory.job_id.in_(job_ids),
                )
                .order_by(desc(JobAssignmentHistory.created_at))
            )
            ja_res = await db.execute(job_assign_stmt)
            for ja in ja_res.scalars().all():
                assign_label = "Lead Recruiter" if ja.assignment_type == "recruiter" else "Hiring Manager"
                events.append(
                    CandidateTimelineItem(
                        id=f"job-assign-{ja.id}",
                        event_type=f"{ja.assignment_type}_assigned",
                        title=f"{assign_label} Assignment Updated",
                        description=f"{assign_label} changed from {ja.previous_user_name or 'Unassigned'} to {ja.new_user_name or 'Unassigned'}",
                        actor_name=ja.actor_name,
                        actor_role="admin",
                        is_internal=True,
                        timestamp=ja.created_at,
                        metadata={"assignment_type": ja.assignment_type, "reason": ja.reason},
                    )
                )

        # Sort all timeline items chronologically descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return CandidateActivityTimelineResponse(
            candidate_id=candidate_id,
            application_id=application_id,
            events=events,
            total_events=len(events),
        )


# Global singleton instance
hr_review_service = HrReviewService()
