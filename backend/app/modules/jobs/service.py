"""Job Discovery and Application Service for Candidate Portal.

Conforms to Step 4.1 candidate experience and immutable application evidence specifications.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import String, delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    EntityNotFoundException,
    ValidationException,
)
from app.core.security.ai_security import sanitize_untrusted_text
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

DANGEROUS_HTML_REGEX = re.compile(
    r"<\s*(script|style|iframe|object|embed|applet|meta|link)[^>]*>.*?<\s*/\s*\1\s*>|"
    r"<\s*(script|style|iframe|object|embed|applet|meta|link)[^>]*>|"
    r"on\w+\s*=\s*([\"'][^\"']*[\"']|[^\s>]+)|"
    r"javascript:[^\s\"'>]+",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_rich_text(text: str | None) -> str:
    """Sanitize rich text descriptions, neutralizing script tags, event handlers, and dangerous attributes."""
    if not text:
        return ""
    cleaned = DANGEROUS_HTML_REGEX.sub("", text)
    return sanitize_untrusted_text(cleaned)


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
        skills: list[str] | str | None = None,
        min_salary: int | None = None,
        max_salary: int | None = None,
        posted_within_days: int | None = None,
        sort_by: str = "recent",
        page: int = 1,
        page_size: int = 20,
    ) -> JobListResponse:
        """Search and filter published jobs with pagination, sorting, and deadline enforcement."""
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        now = datetime.now(UTC)

        # Base filter: Only published jobs and non-expired opportunities
        stmt = (
            select(Job, Organization.name.label("org_name"))
            .join(Organization, Organization.id == Job.tenant_id)
            .where(Job.status == JobStatus.PUBLISHED.value)
            .where(
                or_(
                    Job.application_deadline.is_(None),
                    Job.application_deadline >= now,
                )
            )
        )

        if query and query.strip():
            clean_q = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Job.title.ilike(clean_q),
                    Job.description.ilike(clean_q),
                    Job.department.ilike(clean_q),
                    Job.location.ilike(clean_q),
                    Organization.name.ilike(clean_q),
                    Job.skills_required.cast(String).ilike(clean_q),
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

        if skills:
            skill_list = (
                [s.strip() for s in skills if s.strip()]
                if isinstance(skills, list)
                else [s.strip() for s in skills.split(",") if s.strip()]
            )
            for s in skill_list:
                stmt = stmt.where(Job.skills_required.cast(String).ilike(f"%{s}%"))

        if min_salary is not None and min_salary > 0:
            stmt = stmt.where(
                or_(
                    Job.salary_max >= min_salary,
                    Job.salary_min >= min_salary,
                )
            )

        if max_salary is not None and max_salary > 0:
            stmt = stmt.where(
                or_(
                    Job.salary_min <= max_salary,
                    Job.salary_max <= max_salary,
                )
            )

        if posted_within_days and posted_within_days > 0:
            cutoff = now - timedelta(days=posted_within_days)
            stmt = stmt.where(Job.published_at >= cutoff)

        # Total count query
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await db.execute(count_stmt)
        total = total_res.scalar() or 0

        # Sorting logic with tie-breaker
        if sort_by == "closing_soon":
            stmt = stmt.order_by(
                Job.application_deadline.asc().nulls_last(),
                desc(Job.published_at),
                desc(Job.id),
            )
        elif sort_by == "salary_high":
            stmt = stmt.order_by(
                desc(Job.salary_max).nulls_last(),
                desc(Job.salary_min).nulls_last(),
                desc(Job.published_at),
                desc(Job.id),
            )
        else:  # default "recent"
            stmt = stmt.order_by(
                desc(Job.published_at),
                desc(Job.created_at),
                desc(Job.id),
            )

        # Paginated results
        stmt = stmt.offset(offset).limit(page_size)
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
            is_expired = (
                job.application_deadline is not None and job.application_deadline < now
            ) or job.status != JobStatus.PUBLISHED.value
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
                    description=sanitize_rich_text(job.description),
                    requirements=(
                        sanitize_rich_text(job.requirements) if job.requirements else None
                    ),
                    skills_required=job.skills_required,
                    required_skills=job.skills_required,
                    experience_level=job.experience_level,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    salary_currency=job.salary_currency,
                    status=job.status,
                    published_at=job.published_at,
                    application_deadline=job.application_deadline,
                    is_saved=job.id in saved_job_ids,
                    has_applied=job.id in applied_job_ids,
                    is_expired=is_expired,
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
        """Retrieve single authorized job details with sanitized text and candidate state."""
        stmt = (
            select(Job, Organization.name.label("org_name"))
            .join(Organization, Organization.id == Job.tenant_id)
            .where(Job.id == job_id)
        )
        row = (await db.execute(stmt)).first()
        if not row:
            raise EntityNotFoundException("Job requisition", job_id)

        job, org_name = row
        now = datetime.now(UTC)
        is_expired = (
            job.application_deadline is not None and job.application_deadline < now
        ) or job.status != JobStatus.PUBLISHED.value

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
            description=sanitize_rich_text(job.description),
            requirements=sanitize_rich_text(job.requirements) if job.requirements else None,
            skills_required=job.skills_required,
            required_skills=job.skills_required,
            experience_level=job.experience_level,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            status=job.status,
            published_at=job.published_at,
            application_deadline=job.application_deadline,
            is_saved=is_saved,
            has_applied=has_applied,
            is_expired=is_expired,
        )

    # -------------------------------------------------------------------------
    # Saved Jobs
    # -------------------------------------------------------------------------
    async def save_job(self, db: AsyncSession, user_id: UUID, job_id: UUID) -> None:
        """Save / bookmark a job for later application, preventing duplicates."""
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
        """List all jobs saved by candidate, identifying applied and expired jobs."""
        stmt = (
            select(CandidateSavedJob, Job, Organization.name.label("org_name"))
            .join(Job, Job.id == CandidateSavedJob.job_id)
            .join(Organization, Organization.id == Job.tenant_id)
            .where(CandidateSavedJob.user_id == user_id)
            .order_by(desc(CandidateSavedJob.saved_at))
        )
        rows = (await db.execute(stmt)).all()

        applied_res = await db.execute(
            select(JobApplication.job_id).where(JobApplication.candidate_id == user_id)
        )
        applied_job_ids = set(applied_res.scalars().all())

        now = datetime.now(UTC)
        saved_reads: list[SavedJobRead] = []
        for saved_entry, job, org_name in rows:
            is_expired = (
                job.application_deadline is not None and job.application_deadline < now
            ) or job.status != JobStatus.PUBLISHED.value
            has_applied = job.id in applied_job_ids
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
                description=sanitize_rich_text(job.description),
                requirements=(
                    sanitize_rich_text(job.requirements) if job.requirements else None
                ),
                skills_required=job.skills_required,
                required_skills=job.skills_required,
                experience_level=job.experience_level,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                status=job.status,
                published_at=job.published_at,
                application_deadline=job.application_deadline,
                is_saved=True,
                has_applied=has_applied,
                is_expired=is_expired,
            )
            saved_reads.append(
                SavedJobRead(
                    id=job.id,
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
        answers: dict | None = None,
        consent_records: dict | None = None,
        idempotency_key: str | None = None,
        audit_metadata: dict | None = None,
    ) -> ApplicationSubmitResponse:
        """Submit candidate application with resume version snapshotting, consent, and duplicate protection."""
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

        # 2. Prevent Duplicate Active Applications & Check Idempotency
        app_check = await db.execute(
            select(JobApplication).where(
                JobApplication.candidate_id == candidate_user_id,
                JobApplication.job_id == job_id,
            )
        )
        existing_app = app_check.scalar_one_or_none()
        if existing_app:
            if idempotency_key and getattr(existing_app, "idempotency_key", None) == idempotency_key:
                return ApplicationSubmitResponse(
                    id=existing_app.id,
                    job_id=job.id,
                    candidate_status=existing_app.candidate_status,
                    resume_snapshot_sha256=existing_app.resume_snapshot_sha256,
                    resume_version_applied=getattr(existing_app, "resume_version_applied", 1),
                    message="Application previously submitted (idempotent response)",
                    applied_at=existing_app.applied_at,
                )
            if existing_app.candidate_status == CandidateFacingStatus.WITHDRAWN.value:
                raise ValidationException(
                    "You have previously withdrawn your application for this position. Re-application is not permitted.",
                    code="ERR_APPLICATION_WITHDRAWN",
                )
            raise ValidationException(
                "You have already applied for this position",
                code="ERR_DUPLICATE_APPLICATION",
            )

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

        initial_timeline = [
            {
                "status": CandidateFacingStatus.SUBMITTED.value,
                "changed_at": now.isoformat(),
                "note": "Application received and cryptographic resume snapshot recorded.",
            }
        ]

        target_version = getattr(target_resume, "version_number", 1) or 1
        target_sha256 = getattr(
            target_resume,
            "content_sha256",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

        application = JobApplication(
            id=app_id,
            job_id=job.id,
            candidate_id=candidate_user_id,
            tenant_id=job.tenant_id,
            resume_id=target_resume.id,
            resume_version_applied=target_version,
            resume_snapshot_sha256=target_sha256,
            idempotency_key=idempotency_key,
            status="submitted",
            candidate_status=CandidateFacingStatus.SUBMITTED.value,
            cover_letter=cover_letter.strip() if cover_letter else None,
            answers=answers or {},
            consent_records=consent_records or {},
            timeline=initial_timeline,
            audit_metadata=audit_metadata or {},
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

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException(
                "You have already applied for this position",
                code="ERR_DUPLICATE_APPLICATION",
            ) from exc

        return ApplicationSubmitResponse(
            id=app_id,
            job_id=job.id,
            candidate_status=CandidateFacingStatus.SUBMITTED.value,
            resume_snapshot_sha256=target_sha256,
            resume_version_applied=target_version,
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

        def _safe_dict(v: Any) -> dict | None:
            return v if isinstance(v, dict) else None

        def _safe_list(v: Any) -> list:
            return v if isinstance(v, list) else []

        def _safe_int(v: Any, default: int = 1) -> int:
            return v if isinstance(v, int) else default

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
                    resume_version_applied=_safe_int(getattr(app, "resume_version_applied", 1)),
                    resume_snapshot_sha256=str(getattr(app, "resume_snapshot_sha256", "")),
                    status=str(getattr(app, "status", "submitted")),
                    candidate_status=str(getattr(app, "candidate_status", "submitted")),
                    cover_letter=getattr(app, "cover_letter", None),
                    answers=_safe_dict(getattr(app, "answers", None)),
                    consent_records=_safe_dict(getattr(app, "consent_records", None)),
                    timeline=_safe_list(getattr(app, "timeline", None)),
                    applied_at=app.applied_at,
                    withdrawn_at=getattr(app, "withdrawn_at", None),
                    withdrawal_reason=getattr(app, "withdrawal_reason", None),
                )
            )
        return results

    async def get_candidate_application(
        self, db: AsyncSession, candidate_user_id: UUID, application_id: UUID
    ) -> JobApplicationRead:
        """Retrieve application details with IDOR validation."""
        def _safe_dict(v: Any) -> dict | None:
            return v if isinstance(v, dict) else None

        def _safe_list(v: Any) -> list:
            return v if isinstance(v, list) else []

        def _safe_int(v: Any, default: int = 1) -> int:
            return v if isinstance(v, int) else default

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
            resume_version_applied=_safe_int(getattr(app, "resume_version_applied", 1)),
            resume_snapshot_sha256=str(getattr(app, "resume_snapshot_sha256", "")),
            status=str(getattr(app, "status", "submitted")),
            candidate_status=str(getattr(app, "candidate_status", "submitted")),
            cover_letter=getattr(app, "cover_letter", None),
            answers=_safe_dict(getattr(app, "answers", None)),
            consent_records=_safe_dict(getattr(app, "consent_records", None)),
            timeline=_safe_list(getattr(app, "timeline", None)),
            applied_at=app.applied_at,
            withdrawn_at=getattr(app, "withdrawn_at", None),
            withdrawal_reason=getattr(app, "withdrawal_reason", None),
        )

    async def withdraw_application(
        self, db: AsyncSession, candidate_user_id: UUID, application_id: UUID, reason: str
    ) -> JobApplicationRead:
        """Withdraw candidate application with reason and audit notification."""
        if not reason or not reason.strip():
            raise ValidationException(
                "A valid reason for withdrawal is mandatory", code="ERR_REASON_REQUIRED"
            )

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

        if app.candidate_status in (CandidateFacingStatus.NOT_SELECTED.value, "rejected"):
            raise ValidationException(
                "Cannot withdraw an application that has already concluded",
                code="CANNOT_WITHDRAW_TERMINAL",
            )

        if app.candidate_status in (CandidateFacingStatus.OFFER_STAGE.value, "offer"):
            raise ValidationException(
                "An offer has already been extended for this position. Please contact your hiring recruiter directly.",
                code="CANNOT_WITHDRAW_OFFER",
            )

        now = utc_now()
        app.candidate_status = CandidateFacingStatus.WITHDRAWN.value
        app.status = "withdrawn"
        app.withdrawn_at = now
        app.withdrawal_reason = reason.strip()

        # Update candidate-facing timeline
        timeline_entry = {
            "status": CandidateFacingStatus.WITHDRAWN.value,
            "changed_at": now.isoformat(),
            "note": f"Candidate withdrew application: {reason.strip()}",
        }
        current_timeline = list(getattr(app, "timeline", []) or [])
        current_timeline.append(timeline_entry)
        app.timeline = current_timeline

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
