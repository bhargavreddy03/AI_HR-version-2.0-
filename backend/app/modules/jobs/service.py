"""Job Discovery and Application Service for Candidate Portal.

Conforms to Step 4.1 candidate experience and immutable application evidence specifications.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    EntityNotFoundException,
    ValidationException,
)
from app.modules.candidates.models import (
    CandidateNotification,
    CandidateResume,
    CandidateSavedJob,
)
from app.modules.jobs.models import (
    CandidateFacingStatus,
    Job,
    JobApplication,
    JobStatus,
)
from app.modules.jobs.schemas import (
    ApplicationSubmitResponse,
    JobApplicationRead,
    JobListResponse,
    JobRead,
    SavedJobRead,
)
from app.modules.organizations.models import Organization

logger = logging.getLogger(__name__)


class JobService:
    """Domain service managing public job requisitions, candidate search, and applications."""

    # -------------------------------------------------------------------------
    # Job Discovery & Search
    # -------------------------------------------------------------------------
    async def list_jobs(
        self,
        db: AsyncSession,
        candidate_user_id: UUID | None = None,
        query: str | None = None,
        department: str | None = None,
        location: str | None = None,
        remote_type: str | None = None,
        employment_type: str | None = None,
        experience_level: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> JobListResponse:
        """Search and filter published jobs with pagination."""
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        # Base filter: Only published jobs
        stmt = (
            select(Job, Organization.name.label("org_name"))
            .join(Organization, Organization.id == Job.tenant_id)
            .where(Job.status == JobStatus.PUBLISHED.value)
        )

        if query and query.strip():
            clean_q = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Job.title.ilike(clean_q),
                    Job.description.ilike(clean_q),
                    Job.department.ilike(clean_q),
                )
            )

        if department and department.strip():
            stmt = stmt.where(Job.department.ilike(f"%{department.strip()}%"))

        if location and location.strip():
            stmt = stmt.where(Job.location.ilike(f"%{location.strip()}%"))

        if remote_type and remote_type.strip():
            stmt = stmt.where(Job.remote_type == remote_type.strip().lower())

        if employment_type and employment_type.strip():
            stmt = stmt.where(Job.employment_type == employment_type.strip().lower())

        if experience_level and experience_level.strip():
            stmt = stmt.where(Job.experience_level == experience_level.strip().lower())

        # Total count query
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await db.execute(count_stmt)
        total = total_res.scalar() or 0

        # Paginated results
        stmt = (
            stmt.order_by(desc(Job.published_at), desc(Job.created_at))
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(stmt)).all()

        # Find saved jobs and applied jobs for current candidate
        saved_job_ids: set[UUID] = set()
        applied_job_ids: set[UUID] = set()

        if candidate_user_id:
            saved_res = await db.execute(
                select(CandidateSavedJob.job_id).where(
                    CandidateSavedJob.user_id == candidate_user_id
                )
            )
            saved_job_ids = set(saved_res.scalars().all())

            app_res = await db.execute(
                select(JobApplication.job_id).where(
                    JobApplication.candidate_id == candidate_user_id
                )
            )
            applied_job_ids = set(app_res.scalars().all())

        job_reads: list[JobRead] = []
        for job, org_name in rows:
            job_reads.append(
                JobRead(
                    id=job.id,
                    tenant_id=job.tenant_id,
                    organization_name=org_name,
                    title=job.title,
                    slug=job.slug,
                    department=job.department,
                    location=job.location,
                    remote_type=job.remote_type,
                    employment_type=job.employment_type,
                    description=job.description,
                    requirements=job.requirements,
                    skills_required=job.skills_required,
                    experience_level=job.experience_level,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    salary_currency=job.salary_currency,
                    status=job.status,
                    published_at=job.published_at,
                    application_deadline=job.application_deadline,
                    is_saved=job.id in saved_job_ids,
                    has_applied=job.id in applied_job_ids,
                )
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return JobListResponse(
            jobs=job_reads,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_job(
        self, db: AsyncSession, job_id: UUID, candidate_user_id: UUID | None = None
    ) -> JobRead:
        """Retrieve single job details."""
        stmt = (
            select(Job, Organization.name.label("org_name"))
            .join(Organization, Organization.id == Job.tenant_id)
            .where(Job.id == job_id)
        )
        row = (await db.execute(stmt)).first()
        if not row:
            raise EntityNotFoundException("Job requisition", job_id)

        job, org_name = row

        is_saved = False
        has_applied = False
        if candidate_user_id:
            saved_res = await db.execute(
                select(CandidateSavedJob).where(
                    CandidateSavedJob.user_id == candidate_user_id,
                    CandidateSavedJob.job_id == job_id,
                )
            )
            is_saved = saved_res.scalar_one_or_none() is not None

            app_res = await db.execute(
                select(JobApplication).where(
                    JobApplication.candidate_id == candidate_user_id,
                    JobApplication.job_id == job_id,
                )
            )
            has_applied = app_res.scalar_one_or_none() is not None

        return JobRead(
            id=job.id,
            tenant_id=job.tenant_id,
            organization_name=org_name,
            title=job.title,
            slug=job.slug,
            department=job.department,
            location=job.location,
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            description=job.description,
            requirements=job.requirements,
            skills_required=job.skills_required,
            experience_level=job.experience_level,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            status=job.status,
            published_at=job.published_at,
            application_deadline=job.application_deadline,
            is_saved=is_saved,
            has_applied=has_applied,
        )

    # -------------------------------------------------------------------------
    # Saved Jobs
    # -------------------------------------------------------------------------
    async def save_job(self, db: AsyncSession, user_id: UUID, job_id: UUID) -> None:
        """Save / bookmark a job for later application."""
        # Ensure job exists
        job_res = await db.execute(select(Job.id).where(Job.id == job_id))
        if not job_res.scalar_one_or_none():
            raise EntityNotFoundException("Job requisition", job_id)

        # Check existing bookmark
        existing_res = await db.execute(
            select(CandidateSavedJob).where(
                CandidateSavedJob.user_id == user_id,
                CandidateSavedJob.job_id == job_id,
            )
        )
        if not existing_res.scalar_one_or_none():
            entry = CandidateSavedJob(
                user_id=user_id,
                job_id=job_id,
                saved_at=utc_now(),
            )
            db.add(entry)
            await db.commit()

    async def unsave_job(self, db: AsyncSession, user_id: UUID, job_id: UUID) -> None:
        """Remove job from candidate bookmarks."""
        await db.execute(
            delete(CandidateSavedJob).where(
                CandidateSavedJob.user_id == user_id,
                CandidateSavedJob.job_id == job_id,
            )
        )
        await db.commit()

    async def list_saved_jobs(self, db: AsyncSession, user_id: UUID) -> list[SavedJobRead]:
        """List all jobs saved by candidate."""
        stmt = (
            select(CandidateSavedJob, Job, Organization.name.label("org_name"))
            .join(Job, Job.id == CandidateSavedJob.job_id)
            .join(Organization, Organization.id == Job.tenant_id)
            .where(CandidateSavedJob.user_id == user_id)
            .order_by(desc(CandidateSavedJob.saved_at))
        )
        rows = (await db.execute(stmt)).all()

        saved_reads: list[SavedJobRead] = []
        for saved_entry, job, org_name in rows:
            job_read = JobRead(
                id=job.id,
                tenant_id=job.tenant_id,
                organization_name=org_name,
                title=job.title,
                slug=job.slug,
                department=job.department,
                location=job.location,
                remote_type=job.remote_type,
                employment_type=job.employment_type,
                description=job.description,
                requirements=job.requirements,
                skills_required=job.skills_required,
                experience_level=job.experience_level,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                status=job.status,
                published_at=job.published_at,
                application_deadline=job.application_deadline,
                is_saved=True,
                has_applied=False,
            )
            saved_reads.append(
                SavedJobRead(
                    job_id=job.id,
                    saved_at=saved_entry.saved_at,
                    job=job_read,
                )
            )
        return saved_reads

    # -------------------------------------------------------------------------
    # Job Application Workflow
    # -------------------------------------------------------------------------
    async def apply_to_job(
        self,
        db: AsyncSession,
        candidate_user_id: UUID,
        job_id: UUID,
        resume_id: UUID | None = None,
        cover_letter: str | None = None,
    ) -> ApplicationSubmitResponse:
        """Submit candidate application with resume version snapshotting and duplicate prevention."""
        # 1. Verify Job existence and active status
        job_stmt = (
            select(Job, Organization.name.label("org_name"))
            .join(Organization, Organization.id == Job.tenant_id)
            .where(Job.id == job_id)
        )
        row = (await db.execute(job_stmt)).first()
        if not row:
            raise EntityNotFoundException("Job requisition", job_id)
        job, org_name = row

        if job.status != JobStatus.PUBLISHED.value:
            raise ValidationException(
                "This job requisition is no longer accepting applications",
                code="JOB_NOT_ACCEPTING_APPLICATIONS",
            )

        if job.application_deadline and job.application_deadline < datetime.now(UTC):
            raise ValidationException(
                "The application deadline for this position has passed", code="DEADLINE_PASSED"
            )

        # 2. Prevent Duplicate Active Applications
        app_check = await db.execute(
            select(JobApplication).where(
                JobApplication.candidate_id == candidate_user_id,
                JobApplication.job_id == job_id,
            )
        )
        existing_app = app_check.scalar_one_or_none()
        if existing_app:
            if existing_app.candidate_status != CandidateFacingStatus.WITHDRAWN.value:
                raise ValidationException(
                    "You have already applied for this position",
                    code="ERR_DUPLICATE_APPLICATION",
                )
            # If previously withdrawn, delete old application or reuse
            await db.delete(existing_app)
            await db.flush()

        # 3. Resolve Resume & Snapshot Hash
        target_resume: CandidateResume | None = None
        if resume_id:
            res_query = await db.execute(
                select(CandidateResume).where(
                    CandidateResume.id == resume_id,
                    CandidateResume.user_id == candidate_user_id,
                )
            )
            target_resume = res_query.scalar_one_or_none()
            if not target_resume:
                raise EntityNotFoundException("Resume", resume_id)
        else:
            # Find default resume or latest completed resume
            def_query = await db.execute(
                select(CandidateResume).where(
                    CandidateResume.user_id == candidate_user_id,
                    CandidateResume.is_default == True,  # noqa: E712
                )
            )
            target_resume = def_query.scalar_one_or_none()

            if not target_resume:
                latest_query = await db.execute(
                    select(CandidateResume)
                    .where(CandidateResume.user_id == candidate_user_id)
                    .order_by(desc(CandidateResume.created_at))
                    .limit(1)
                )
                target_resume = latest_query.scalar_one_or_none()

        if not target_resume:
            raise ValidationException(
                "A resume is required to apply. Please upload a resume before applying.",
                code="ERR_RESUME_REQUIRED",
            )

        now = utc_now()
        app_id = generate_uuid7()

        application = JobApplication(
            id=app_id,
            job_id=job.id,
            candidate_id=candidate_user_id,
            tenant_id=job.tenant_id,
            resume_id=target_resume.id,
            resume_snapshot_sha256=target_resume.content_sha256,
            status="submitted",
            candidate_status=CandidateFacingStatus.SUBMITTED.value,
            cover_letter=cover_letter.strip() if cover_letter else None,
            applied_at=now,
        )
        db.add(application)

        # 4. Generate In-App Notification
        notif = CandidateNotification(
            id=generate_uuid7(),
            user_id=candidate_user_id,
            title="Application Submitted",
            message=f"Your application for {job.title} at {org_name} has been received.",
            category="application_update",
            is_read=False,
            action_url=f"/candidate/applications/{app_id}",
        )
        db.add(notif)

        await db.commit()

        return ApplicationSubmitResponse(
            id=app_id,
            job_id=job.id,
            candidate_status=CandidateFacingStatus.SUBMITTED.value,
            message="Application submitted successfully",
            applied_at=now,
        )

    # -------------------------------------------------------------------------
    # Application Tracking
    # -------------------------------------------------------------------------
    async def list_candidate_applications(
        self, db: AsyncSession, candidate_user_id: UUID
    ) -> list[JobApplicationRead]:
        """List all applications submitted by the candidate with timeline and details."""
        stmt = (
            select(
                JobApplication,
                Job.title.label("job_title"),
                Job.department.label("job_department"),
                Job.location.label("job_location"),
                Job.remote_type.label("job_remote_type"),
                Organization.name.label("org_name"),
                CandidateResume.filename.label("resume_filename"),
            )
            .join(Job, Job.id == JobApplication.job_id)
            .join(Organization, Organization.id == JobApplication.tenant_id)
            .outerjoin(CandidateResume, CandidateResume.id == JobApplication.resume_id)
            .where(JobApplication.candidate_id == candidate_user_id)
            .order_by(desc(JobApplication.applied_at))
        )
        rows = (await db.execute(stmt)).all()

        results: list[JobApplicationRead] = []
        for app, j_title, j_dept, j_loc, j_remote, org_name, resume_fn in rows:
            results.append(
                JobApplicationRead(
                    id=app.id,
                    job_id=app.job_id,
                    candidate_id=app.candidate_id,
                    tenant_id=app.tenant_id,
                    organization_name=org_name,
                    job_title=j_title,
                    job_department=j_dept,
                    job_location=j_loc,
                    remote_type=j_remote,
                    resume_id=app.resume_id,
                    resume_filename=resume_fn,
                    resume_snapshot_sha256=app.resume_snapshot_sha256,
                    status=app.status,
                    candidate_status=app.candidate_status,
                    cover_letter=app.cover_letter,
                    applied_at=app.applied_at,
                    withdrawn_at=app.withdrawn_at,
                    withdrawal_reason=app.withdrawal_reason,
                )
            )
        return results

    async def get_candidate_application(
        self, db: AsyncSession, candidate_user_id: UUID, application_id: UUID
    ) -> JobApplicationRead:
        """Retrieve application details with IDOR validation."""
        stmt = (
            select(
                JobApplication,
                Job.title.label("job_title"),
                Job.department.label("job_department"),
                Job.location.label("job_location"),
                Job.remote_type.label("job_remote_type"),
                Organization.name.label("org_name"),
                CandidateResume.filename.label("resume_filename"),
            )
            .join(Job, Job.id == JobApplication.job_id)
            .join(Organization, Organization.id == JobApplication.tenant_id)
            .outerjoin(CandidateResume, CandidateResume.id == JobApplication.resume_id)
            .where(
                JobApplication.id == application_id,
                JobApplication.candidate_id == candidate_user_id,
            )
        )
        row = (await db.execute(stmt)).first()
        if not row:
            raise EntityNotFoundException("Application", application_id)

        app, j_title, j_dept, j_loc, j_remote, org_name, resume_fn = row
        return JobApplicationRead(
            id=app.id,
            job_id=app.job_id,
            candidate_id=app.candidate_id,
            tenant_id=app.tenant_id,
            organization_name=org_name,
            job_title=j_title,
            job_department=j_dept,
            job_location=j_loc,
            remote_type=j_remote,
            resume_id=app.resume_id,
            resume_filename=resume_fn,
            resume_snapshot_sha256=app.resume_snapshot_sha256,
            status=app.status,
            candidate_status=app.candidate_status,
            cover_letter=app.cover_letter,
            applied_at=app.applied_at,
            withdrawn_at=app.withdrawn_at,
            withdrawal_reason=app.withdrawal_reason,
        )

    async def withdraw_application(
        self, db: AsyncSession, candidate_user_id: UUID, application_id: UUID, reason: str
    ) -> JobApplicationRead:
        """Withdraw candidate application with reason and audit notification."""
        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.candidate_id == candidate_user_id,
        )
        res = await db.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            raise EntityNotFoundException("Application", application_id)

        if app.candidate_status == CandidateFacingStatus.WITHDRAWN.value:
            raise ValidationException(
                "This application has already been withdrawn", code="ALREADY_WITHDRAWN"
            )

        app.candidate_status = CandidateFacingStatus.WITHDRAWN.value
        app.status = "withdrawn"
        app.withdrawn_at = utc_now()
        app.withdrawal_reason = reason.strip()

        # Add candidate notification
        notif = CandidateNotification(
            id=generate_uuid7(),
            user_id=candidate_user_id,
            title="Application Withdrawn",
            message="Your application has been withdrawn.",
            category="application_update",
            is_read=False,
            action_url=f"/candidate/applications/{app.id}",
        )
        db.add(notif)

        await db.commit()
        return await self.get_candidate_application(db, candidate_user_id, application_id)


job_service = JobService()
