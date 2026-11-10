"""HR Applicant and Candidate Management Service.

Enforces strict tenant isolation, candidate privacy, secure resume access, and server-side pagination.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import utc_now
from app.core.errors import (
    AppException,
    AuthorizationException,
    EntityNotFoundException,
)
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.candidates.models import (
    CandidateCertification,
    CandidateEducation,
    CandidateExperience,
    CandidateLanguage,
    CandidateProject,
    CandidateResume,
)
from app.modules.documents.storage import StorageService
from app.modules.hr.applicant_schemas import (
    ApplicantListItem,
    ApplicantListResponse,
    ApplicationDetailContext,
    BulkRecruiterAssignResponse,
    CandidateComparisonItem,
    CandidateComparisonResponse,
    CandidateDetailCertification,
    CandidateDetailEducation,
    CandidateDetailExperience,
    CandidateDetailLanguage,
    CandidateDetailProject,
    CandidateDetailResponse,
    OrganizationApplicationSummary,
    ResumeSignedUrlResponse,
    TimelineEventItem,
)
from app.modules.jobs.models import Job, JobApplication
from app.modules.organizations.models import OrganizationMembership

logger = logging.getLogger(__name__)


def _parse_date_to_year_fraction(date_str: str | None) -> float | None:
    """Safely parse a date string into year + month/12 fraction."""
    if not date_str:
        return None
    cleaned = date_str.strip()
    # Match YYYY-MM or YYYY-MM-DD
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", cleaned)
    if m:
        year = int(m.group(1))
        month = int(m.group(2)) if m.group(2) else 1
        return year + (month - 1) / 12.0
    # Try 4-digit year anywhere
    m_year = re.search(r"\b(19\d\d|20\d\d)\b", cleaned)
    if m_year:
        return float(m_year.group(1))
    return None


def calculate_experience_years(experiences: list[CandidateExperience]) -> float:
    """Calculate cumulative years of professional experience across candidate roles."""
    if not experiences:
        return 0.0

    now = datetime.now(UTC)
    current_year_fraction = now.year + (now.month - 1) / 12.0
    total_years = 0.0

    for exp in experiences:
        start = _parse_date_to_year_fraction(exp.start_date)
        if start is None:
            continue
        if exp.is_current or not exp.end_date:
            end = current_year_fraction
        else:
            end = _parse_date_to_year_fraction(exp.end_date) or start
        diff = max(0.0, end - start)
        total_years += diff

    return round(total_years, 1)


class HrApplicantService:
    """Service handling HR applicant listings, candidate profile views, and resume access."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        self.storage_service = storage_service or StorageService()

    async def list_applicants(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        search: str | None = None,
        job_id: UUID | None = None,
        department: str | None = None,
        status: str | None = None,
        recruiter_id: UUID | None = None,
        location: str | None = None,
        skills: str | None = None,
        min_experience_years: float | None = None,
        max_experience_years: float | None = None,
        applied_after: datetime | None = None,
        applied_before: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "applied_at",
        sort_order: str = "desc",
    ) -> ApplicantListResponse:
        """Query organization-authorized job applications with candidate identity and metadata."""
        # 1. Base filter: strictly tenant scoped
        filters = [JobApplication.tenant_id == tenant_id]

        if job_id:
            filters.append(JobApplication.job_id == job_id)
        if department:
            filters.append(Job.department.ilike(f"%{department.strip()}%"))
        if status:
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                filters.append(JobApplication.status == statuses[0])
            elif len(statuses) > 1:
                filters.append(JobApplication.status.in_(statuses))
        if recruiter_id:
            filters.append(Job.recruiter_id == recruiter_id)
        if location:
            filters.append(
                or_(
                    Job.location.ilike(f"%{location.strip()}%"),
                    CandidateUserProfile.location_city.ilike(f"%{location.strip()}%"),
                    CandidateUserProfile.location_country.ilike(f"%{location.strip()}%"),
                )
            )
        if applied_after:
            filters.append(JobApplication.applied_at >= applied_after)
        if applied_before:
            filters.append(JobApplication.applied_at <= applied_before)

        # Candidate user alias & relationships
        candidate_user = User
        recruiter_user = selectinload(Job.recruiter)
        hm_user = selectinload(Job.hiring_manager)

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
            .options(recruiter_user, hm_user)
            .where(*filters)
        )

        # Search filter
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

        # Count total records matching filters
        count_stmt = (
            select(func.count(JobApplication.id))
            .join(Job, Job.id == JobApplication.job_id)
            .join(candidate_user, candidate_user.id == JobApplication.candidate_id)
            .outerjoin(CandidateUserProfile, CandidateUserProfile.user_id == candidate_user.id)
            .where(*filters)
        )
        if search and search.strip():
            term = f"%{search.strip()}%"
            count_stmt = count_stmt.where(
                or_(
                    candidate_user.first_name.ilike(term),
                    candidate_user.last_name.ilike(term),
                    candidate_user.email.ilike(term),
                    Job.title.ilike(term),
                    CandidateUserProfile.headline.ilike(term),
                )
            )
        total_count = (await db.execute(count_stmt)).scalar() or 0

        # Sort order
        sort_col = JobApplication.applied_at
        if sort_by == "candidate_name":
            sort_col = candidate_user.last_name
        elif sort_by == "job_title":
            sort_col = Job.title
        elif sort_by == "status":
            sort_col = JobApplication.status

        order_clause = desc(sort_col) if sort_order.lower() == "desc" else sort_col.asc()
        offset = max(0, (page - 1) * page_size)
        query = query.order_by(order_clause).offset(offset).limit(page_size)

        rows = (await db.execute(query)).all()
        if not rows:
            return ApplicantListResponse(
                items=[],
                total=total_count,
                page=page,
                page_size=page_size,
                pages=max(1, (total_count + page_size - 1) // page_size),
            )

        # Fetch experiences for candidates in this page to compute experience years and current job
        candidate_ids = list({row[0].candidate_id for row in rows})
        exp_stmt = (
            select(CandidateExperience)
            .where(CandidateExperience.user_id.in_(candidate_ids))
            .order_by(CandidateExperience.is_current.desc())
        )
        exp_rows = (await db.execute(exp_stmt)).scalars().all()
        experiences_by_user: dict[UUID, list[CandidateExperience]] = {}
        for exp in exp_rows:
            experiences_by_user.setdefault(exp.user_id, []).append(exp)

        items: list[ApplicantListItem] = []
        for app, job, user, profile, resume in rows:
            user_exps = experiences_by_user.get(app.candidate_id, [])
            exp_years = calculate_experience_years(user_exps)

            # Find current role
            current_role = next((e for e in user_exps if e.is_current), None) or (
                user_exps[0] if user_exps else None
            )

            # Combined skills
            combined_skills = set(profile.self_declared_skills or []) if profile else set()
            if resume and resume.skills_extracted:
                combined_skills.update(resume.skills_extracted)
            for exp in user_exps:
                if exp.skills:
                    combined_skills.update(exp.skills)

            # Candidate location string
            loc_parts = []
            if profile and profile.location_city:
                loc_parts.append(profile.location_city)
            if profile and profile.location_country:
                loc_parts.append(profile.location_country)
            cand_location = ", ".join(loc_parts) if loc_parts else None

            # Recruiter / Hiring manager names
            recruiter_name = (
                f"{job.recruiter.first_name} {job.recruiter.last_name}" if job.recruiter else None
            )
            hm_name = (
                f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}"
                if job.hiring_manager
                else None
            )

            # Compute last activity
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

            items.append(
                ApplicantListItem(
                    id=app.id,
                    candidate_id=app.candidate_id,
                    candidate_name=f"{user.first_name} {user.last_name}",
                    candidate_email=user.email,
                    candidate_phone=profile.phone if profile else user.phone_number,
                    candidate_headline=profile.headline if profile else None,
                    candidate_location=cand_location,
                    candidate_avatar_url=user.avatar_url,
                    job_id=job.id,
                    job_title=job.title,
                    job_department=job.department,
                    job_location=job.location,
                    status=app.status,
                    candidate_status=app.candidate_status,
                    applied_at=app.applied_at,
                    skills=sorted(combined_skills),
                    experience_years=exp_years,
                    current_job_title=current_role.job_title if current_role else None,
                    current_company=current_role.company_name if current_role else None,
                    resume_available=bool(app.resume_id or app.resume_snapshot_sha256),
                    resume_id=app.resume_id,
                    resume_filename=resume.filename if resume else None,
                    resume_snapshot_sha256=app.resume_snapshot_sha256,
                    recruiter_id=job.recruiter_id,
                    recruiter_name=recruiter_name,
                    hiring_manager_id=job.hiring_manager_id,
                    hiring_manager_name=hm_name,
                    last_activity_at=last_activity,
                )
            )

        # In-memory post-filtering for experience years and skills if requested
        if min_experience_years is not None:
            items = [item for item in items if item.experience_years >= min_experience_years]
        if max_experience_years is not None:
            items = [item for item in items if item.experience_years <= max_experience_years]
        if skills and skills.strip():
            filter_skills = {s.strip().lower() for s in skills.split(",") if s.strip()}
            items = [
                item
                for item in items
                if any(fs in {sk.lower() for sk in item.skills} for fs in filter_skills)
            ]

        pages = max(1, (total_count + page_size - 1) // page_size)
        return ApplicantListResponse(
            items=items,
            total=total_count,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_candidate_details(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        candidate_id: UUID,
        application_id: UUID | None = None,
    ) -> CandidateDetailResponse:
        """Fetch comprehensive candidate profile with strict tenant boundary enforcement."""
        # 1. Candidate Privacy Check: Candidate must have at least one application to THIS organization
        auth_check = await db.execute(
            select(JobApplication.id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.tenant_id == tenant_id,
            )
            .limit(1)
        )
        if not auth_check.scalar_one_or_none():
            raise AuthorizationException(
                message="Candidate profile is not accessible: no application submitted to this organization.",
                error_code="CANDIDATE_ACCESS_FORBIDDEN",
            )

        # 2. Fetch User identity and Profile
        user_res = await db.execute(select(User).where(User.id == candidate_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise EntityNotFoundException("Candidate User", candidate_id)

        profile_res = await db.execute(
            select(CandidateUserProfile).where(CandidateUserProfile.user_id == candidate_id)
        )
        profile = profile_res.scalar_one_or_none()

        # 3. Fetch candidate portfolio records
        exps_res = await db.execute(
            select(CandidateExperience)
            .where(CandidateExperience.user_id == candidate_id)
            .order_by(CandidateExperience.is_current.desc(), CandidateExperience.created_at.desc())
        )
        experiences = list(exps_res.scalars().all())

        edus_res = await db.execute(
            select(CandidateEducation)
            .where(CandidateEducation.user_id == candidate_id)
            .order_by(desc(CandidateEducation.end_year))
        )
        educations = list(edus_res.scalars().all())

        certs_res = await db.execute(
            select(CandidateCertification)
            .where(CandidateCertification.user_id == candidate_id)
            .order_by(CandidateCertification.created_at.desc())
        )
        certifications = list(certs_res.scalars().all())

        projs_res = await db.execute(
            select(CandidateProject)
            .where(CandidateProject.user_id == candidate_id)
            .order_by(CandidateProject.created_at.desc())
        )
        projects = list(projs_res.scalars().all())

        langs_res = await db.execute(
            select(CandidateLanguage)
            .where(CandidateLanguage.user_id == candidate_id)
            .order_by(CandidateLanguage.created_at.desc())
        )
        languages = list(langs_res.scalars().all())

        # Calculate combined skills and experience years
        exp_years = calculate_experience_years(experiences)
        combined_skills = set(profile.self_declared_skills or []) if profile else set()
        for exp in experiences:
            if exp.skills:
                combined_skills.update(exp.skills)
        for proj in projects:
            if proj.skills:
                combined_skills.update(proj.skills)

        # 4. Fetch Organization-scoped Application History (STRICTLY THIS TENANT)
        history_res = await db.execute(
            select(JobApplication, Job)
            .join(Job, Job.id == JobApplication.job_id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.tenant_id == tenant_id,
            )
            .order_by(desc(JobApplication.applied_at))
        )
        history_rows = history_res.all()
        org_apps: list[OrganizationApplicationSummary] = [
            OrganizationApplicationSummary(
                application_id=app.id,
                job_id=job.id,
                job_title=job.title,
                department=job.department,
                applied_at=app.applied_at,
                status=app.status,
                candidate_status=app.candidate_status,
                withdrawn_at=app.withdrawn_at,
            )
            for app, job in history_rows
        ]

        # 5. Fetch current application context if application_id is provided or take first
        target_app_id = application_id or (org_apps[0].application_id if org_apps else None)
        current_app_ctx: ApplicationDetailContext | None = None

        if target_app_id:
            target_res = await db.execute(
                select(JobApplication, Job, CandidateResume)
                .join(Job, Job.id == JobApplication.job_id)
                .outerjoin(CandidateResume, CandidateResume.id == JobApplication.resume_id)
                .options(selectinload(Job.recruiter), selectinload(Job.hiring_manager))
                .where(
                    JobApplication.id == target_app_id,
                    JobApplication.tenant_id == tenant_id,
                )
            )
            target_row = target_res.first()
            if target_row:
                t_app, t_job, t_resume = target_row

                # Add resume skills to combined skills
                if t_resume and t_resume.skills_extracted:
                    combined_skills.update(t_resume.skills_extracted)

                # Split timeline events into candidate-visible and internal
                cand_timeline: list[TimelineEventItem] = []
                int_timeline: list[TimelineEventItem] = []

                raw_timeline = t_app.timeline or []
                for entry in raw_timeline:
                    if isinstance(entry, dict):
                        is_internal = bool(entry.get("is_internal", False))
                        event_item = TimelineEventItem(
                            status=entry.get("status", "update"),
                            changed_at=entry.get("changed_at", t_app.applied_at.isoformat()),
                            note=entry.get("note"),
                            actor_name=entry.get("actor_name"),
                            actor_role=entry.get("actor_role"),
                            is_internal=is_internal,
                        )
                        if is_internal:
                            int_timeline.append(event_item)
                        else:
                            cand_timeline.append(event_item)

                rec_name = (
                    f"{t_job.recruiter.first_name} {t_job.recruiter.last_name}"
                    if t_job.recruiter
                    else None
                )
                hm_name = (
                    f"{t_job.hiring_manager.first_name} {t_job.hiring_manager.last_name}"
                    if t_job.hiring_manager
                    else None
                )

                current_app_ctx = ApplicationDetailContext(
                    application_id=t_app.id,
                    job_id=t_job.id,
                    job_title=t_job.title,
                    job_department=t_job.department,
                    job_location=t_job.location,
                    recruiter_id=t_job.recruiter_id,
                    recruiter_name=rec_name,
                    hiring_manager_id=t_job.hiring_manager_id,
                    hiring_manager_name=hm_name,
                    status=t_app.status,
                    candidate_status=t_app.candidate_status,
                    applied_at=t_app.applied_at,
                    cover_letter=t_app.cover_letter,
                    answers=t_app.answers or {},
                    resume_id=t_app.resume_id,
                    resume_version_applied=t_app.resume_version_applied,
                    resume_snapshot_sha256=t_app.resume_snapshot_sha256,
                    resume_filename=t_resume.filename if t_resume else None,
                    candidate_timeline=cand_timeline,
                    internal_timeline=int_timeline,
                )

        return CandidateDetailResponse(
            candidate_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=f"{user.first_name} {user.last_name}",
            email=user.email,
            phone_number=profile.phone if profile else user.phone_number,
            avatar_url=user.avatar_url,
            headline=profile.headline if profile else None,
            bio=profile.bio if profile else None,
            location_city=profile.location_city if profile else None,
            location_country=profile.location_country if profile else None,
            preferred_title=profile.preferred_title if profile else None,
            work_authorization=profile.work_authorization if profile else None,
            portfolio_urls=(profile.portfolio_urls or []) if profile else [],
            skills=sorted(combined_skills),
            experience_years=exp_years,
            experiences=[CandidateDetailExperience.model_validate(e) for e in experiences],
            educations=[CandidateDetailEducation.model_validate(e) for e in educations],
            certifications=[CandidateDetailCertification.model_validate(c) for c in certifications],
            projects=[CandidateDetailProject.model_validate(p) for p in projects],
            languages=[CandidateDetailLanguage.model_validate(lang) for lang in languages],
            current_application=current_app_ctx,
            organization_application_history=org_apps,
        )

    async def get_resume_signed_url(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_id: UUID,
        actor_user_id: UUID,
    ) -> ResumeSignedUrlResponse:
        """Generate short-lived signed URL for resume download with tenant check & audit logging."""
        # 1. Query application strictly scoped to tenant
        app_res = await db.execute(
            select(JobApplication).where(
                JobApplication.id == application_id,
                JobApplication.tenant_id == tenant_id,
            )
        )
        app = app_res.scalar_one_or_none()
        if not app:
            raise EntityNotFoundException("JobApplication", application_id)

        # 2. Query resume record
        resume: CandidateResume | None = None
        if app.resume_id:
            res_res = await db.execute(
                select(CandidateResume).where(CandidateResume.id == app.resume_id)
            )
            resume = res_res.scalar_one_or_none()

        if not resume and app.resume_snapshot_sha256:
            # Fallback by content sha256
            res_res = await db.execute(
                select(CandidateResume).where(
                    CandidateResume.user_id == app.candidate_id,
                    CandidateResume.content_sha256 == app.resume_snapshot_sha256,
                )
            )
            resume = res_res.scalar_one_or_none()

        if not resume:
            raise AppException(
                message="No resume document found for this application.",
                status_code=404,
                code="RESUME_NOT_FOUND",
            )

        # Verify candidate ownership
        if resume.user_id != app.candidate_id:
            raise AuthorizationException(
                message="Resume ownership integrity violation.",
                error_code="RESUME_ACCESS_VIOLATION",
            )

        # 3. Generate presigned URL (15 minutes expiry)
        presigned_url = self.storage_service.generate_presigned_download_url(
            resume.storage_key, expire_seconds=900
        )

        # 4. Audit Log in application audit metadata
        audit = app.audit_metadata if isinstance(app.audit_metadata, dict) else {}
        access_log = audit.get("resume_access_history", [])
        access_log.append(
            {
                "actor_id": str(actor_user_id),
                "accessed_at": utc_now().isoformat(),
                "resume_id": str(resume.id),
                "storage_key": resume.storage_key,
            }
        )
        audit["resume_access_history"] = access_log
        app.audit_metadata = audit

        # Add internal timeline event
        current_timeline = list(app.timeline or [])
        current_timeline.append(
            {
                "status": "resume_viewed",
                "changed_at": utc_now().isoformat(),
                "note": f"Resume ({resume.filename}) viewed or downloaded by authorized HR user.",
                "is_internal": True,
            }
        )
        app.timeline = current_timeline
        await db.commit()

        return ResumeSignedUrlResponse(
            application_id=app.id,
            candidate_id=app.candidate_id,
            resume_id=resume.id,
            filename=resume.filename,
            mime_type=resume.mime_type,
            file_size_bytes=resume.file_size_bytes,
            content_sha256=resume.content_sha256,
            download_url=presigned_url,
            expires_in_seconds=900,
        )

    async def compare_candidates(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_ids: list[UUID],
    ) -> CandidateComparisonResponse:
        """Side-by-side comparison matrix for 2 to 4 candidates under the same organization."""
        if len(application_ids) < 2 or len(application_ids) > 4:
            raise AppException(
                message="Candidate comparison requires between 2 and 4 applications.",
                status_code=400,
                code="INVALID_COMPARISON_COUNT",
            )

        stmt = (
            select(JobApplication, Job, User, CandidateUserProfile, CandidateResume)
            .join(Job, Job.id == JobApplication.job_id)
            .join(User, User.id == JobApplication.candidate_id)
            .outerjoin(CandidateUserProfile, CandidateUserProfile.user_id == User.id)
            .outerjoin(CandidateResume, CandidateResume.id == JobApplication.resume_id)
            .where(
                JobApplication.id.in_(application_ids),
                JobApplication.tenant_id == tenant_id,
            )
        )
        rows = (await db.execute(stmt)).all()
        if len(rows) != len(application_ids):
            raise AppException(
                message="One or more specified applications do not exist or belong to another organization.",
                status_code=404,
                code="CROSS_TENANT_COMPARISON_FORBIDDEN",
            )

        # Fetch experiences and educations for these candidates
        candidate_ids = [r[0].candidate_id for r in rows]
        exps_res = await db.execute(
            select(CandidateExperience).where(CandidateExperience.user_id.in_(candidate_ids))
        )
        edus_res = await db.execute(
            select(CandidateEducation).where(CandidateEducation.user_id.in_(candidate_ids))
        )

        exps_by_cand: dict[UUID, list[CandidateExperience]] = {}
        for exp in exps_res.scalars().all():
            exps_by_cand.setdefault(exp.user_id, []).append(exp)

        edus_by_cand: dict[UUID, list[CandidateEducation]] = {}
        for edu in edus_res.scalars().all():
            edus_by_cand.setdefault(edu.user_id, []).append(edu)

        items: list[CandidateComparisonItem] = []
        job_title = rows[0][1].title if rows else None
        job_id = rows[0][1].id if rows else None

        for app, job, user, profile, resume in rows:
            user_exps = exps_by_cand.get(app.candidate_id, [])
            user_edus = edus_by_cand.get(app.candidate_id, [])
            exp_years = calculate_experience_years(user_exps)

            current_role = next((e for e in user_exps if e.is_current), None) or (
                user_exps[0] if user_exps else None
            )
            highest_edu = user_edus[0].degree if user_edus else None

            # Candidate skills
            cand_skills = set(profile.self_declared_skills or []) if profile else set()
            if resume and resume.skills_extracted:
                cand_skills.update(resume.skills_extracted)
            for exp in user_exps:
                if exp.skills:
                    cand_skills.update(exp.skills)

            # Match against job required skills
            job_req_skills = job.skills_required or []
            cand_set = {s.lower() for s in cand_skills}

            matching = [s for s in job_req_skills if s.lower() in cand_set]
            missing = [s for s in job_req_skills if s.lower() not in cand_set]
            match_pct = (
                round((len(matching) / len(job_req_skills) * 100.0), 1) if job_req_skills else 100.0
            )

            items.append(
                CandidateComparisonItem(
                    application_id=app.id,
                    candidate_id=app.candidate_id,
                    candidate_name=f"{user.first_name} {user.last_name}",
                    candidate_email=user.email,
                    job_id=job.id,
                    job_title=job.title,
                    status=app.status,
                    applied_at=app.applied_at,
                    experience_years=exp_years,
                    current_job_title=current_role.job_title if current_role else None,
                    current_company=current_role.company_name if current_role else None,
                    highest_education=highest_edu,
                    skills=sorted(cand_skills),
                    job_skills_required=job_req_skills,
                    matching_skills=matching,
                    missing_skills=missing,
                    match_percentage=match_pct,
                    resume_available=bool(app.resume_id or app.resume_snapshot_sha256),
                )
            )

        return CandidateComparisonResponse(
            job_id=job_id,
            job_title=job_title,
            candidates=items,
        )

    async def bulk_assign_recruiter(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        application_ids: list[UUID],
        recruiter_id: UUID,
        actor_id: UUID,
    ) -> BulkRecruiterAssignResponse:
        """Bulk-assign lead recruiter to selected organization applications."""
        # Verify recruiter membership in organization
        mem_res = await db.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == recruiter_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        mem_row = mem_res.first()
        if not mem_row:
            raise EntityNotFoundException("Recruiter Membership", recruiter_id)
        _, recruiter_user = mem_row

        # Verify all application IDs belong to this tenant
        apps_res = await db.execute(
            select(JobApplication).where(
                JobApplication.id.in_(application_ids),
                JobApplication.tenant_id == tenant_id,
            )
        )
        apps = list(apps_res.scalars().all())
        if len(apps) != len(application_ids):
            raise AppException(
                message="One or more selected applications do not exist or belong to another organization.",
                status_code=404,
                code="CROSS_TENANT_ASSIGNMENT_FORBIDDEN",
            )

        # Update applications internal timeline / metadata
        recruiter_full_name = f"{recruiter_user.first_name} {recruiter_user.last_name}"
        for app in apps:
            current_tl = list(app.timeline or [])
            current_tl.append(
                {
                    "status": "recruiter_assigned",
                    "changed_at": utc_now().isoformat(),
                    "note": f"Recruiter assigned to {recruiter_full_name}",
                    "is_internal": True,
                }
            )
            app.timeline = current_tl

        await db.commit()

        return BulkRecruiterAssignResponse(
            updated_count=len(apps),
            application_ids=application_ids,
            recruiter_id=recruiter_id,
            recruiter_name=recruiter_full_name,
        )


hr_applicant_service = HrApplicantService()
