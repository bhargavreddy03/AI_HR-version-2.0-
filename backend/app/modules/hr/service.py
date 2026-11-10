"""HR Dashboard service orchestrating organization-scoped recruitment metrics and analytics.

Conforms strictly to Step 4.2 multi-tenant isolation specifications.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, desc, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import generate_uuid7, utc_now
from app.core.errors import AppException, ConflictException
from app.modules.auth.models import User
from app.modules.hr.requisition_schemas import (
    CanonicalSkillSuggestion,
    JobRequisitionCreate,
    JobRequisitionListResponse,
    JobRequisitionRead,
    JobRequisitionUpdate,
    TeamMemberOption,
)
from app.modules.hr.schemas import (
    ApplicationsOverTimePoint,
    DepartmentApplicationCount,
    FunnelStageCount,
    HrDashboardMetrics,
    HrDashboardOverviewResponse,
    JobApplicationCount,
    RecentActivityItem,
    RecentApplicantItem,
)
from app.modules.jobs.models import Job, JobApplication
from app.modules.organizations.models import Organization, OrganizationMembership, Role
from app.modules.screening.skills.registry import skill_registry

logger = logging.getLogger(__name__)


class HrDashboardService:
    """Service providing organization-isolated recruitment KPI aggregations."""

    async def get_dashboard_overview(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        department: str | None = None,
        job_id: UUID | None = None,
        location: str | None = None,
        employment_type: str | None = None,
        stage: str | None = None,
    ) -> HrDashboardOverviewResponse:
        """Calculate real organization-scoped metrics and visualizations from actual database records."""
        # 1. Resolve Organization Name
        org_res = await db.execute(select(Organization).where(Organization.id == tenant_id))
        org = org_res.scalar_one_or_none()
        org_name = org.name if org else "Organization"

        # 2. Build Base Filter Clauses for Applications
        app_filters = [JobApplication.tenant_id == tenant_id]
        job_filters = [Job.tenant_id == tenant_id]

        if start_date:
            app_filters.append(JobApplication.applied_at >= start_date)
        if end_date:
            app_filters.append(JobApplication.applied_at <= end_date)
        if department:
            job_filters.append(Job.department.ilike(f"%{department}%"))
        if job_id:
            app_filters.append(JobApplication.job_id == job_id)
            job_filters.append(Job.id == job_id)
        if location:
            job_filters.append(Job.location.ilike(f"%{location}%"))
        if employment_type:
            job_filters.append(Job.employment_type == employment_type)
        if stage:
            app_filters.append(JobApplication.status.ilike(stage))

        # 3. Calculate High-Level Application Metrics
        app_metric_query = (
            select(
                func.count(JobApplication.id).label("total_applications"),
                func.count(distinct(JobApplication.candidate_id)).label("total_candidates"),
                func.count(
                    case(
                        (
                            JobApplication.status.in_(["submitted", "under_review", "applied"]),
                            JobApplication.id,
                        )
                    )
                ).label("awaiting_review"),
                func.count(
                    case((JobApplication.status == "shortlisted", JobApplication.id))
                ).label("shortlisted"),
                func.count(
                    case(
                        (
                            JobApplication.status.in_(["interviewing", "interview_stage", "interview"]),
                            JobApplication.id,
                        )
                    )
                ).label("scheduled_interviews"),
                func.count(
                    case(
                        (
                            JobApplication.status.in_(["hired", "offer_accepted"]),
                            JobApplication.id,
                        )
                    )
                ).label("hired"),
            )
            .join(Job, JobApplication.job_id == Job.id)
            .where(and_(*app_filters, *job_filters))
        )
        app_metrics_row = (await db.execute(app_metric_query)).one()

        # 4. Calculate Job Opening Metrics
        now = utc_now()
        job_metric_query = select(
            func.count(
                case(
                    (
                        and_(
                            Job.status == "published",
                            (Job.application_deadline.is_(None) | (Job.application_deadline >= now)),
                        ),
                        Job.id,
                    )
                )
            ).label("active_jobs"),
            func.count(case((Job.status == "published", Job.id))).label("published_jobs"),
            func.count(
                case((Job.status.in_(["draft", "pending_approval"]), Job.id))
            ).label("draft_jobs"),
        ).where(and_(*job_filters))
        job_metrics_row = (await db.execute(job_metric_query)).one()

        total_apps = int(app_metrics_row.total_applications or 0)
        total_cands = int(app_metrics_row.total_candidates or 0)
        awaiting_rev = int(app_metrics_row.awaiting_review or 0)
        shortlisted = int(app_metrics_row.shortlisted or 0)
        interviews = int(app_metrics_row.scheduled_interviews or 0)
        hired = int(app_metrics_row.hired or 0)

        metrics = HrDashboardMetrics(
            total_candidates=total_cands,
            total_applications=total_apps,
            active_jobs=int(job_metrics_row.active_jobs or 0),
            published_jobs=int(job_metrics_row.published_jobs or 0),
            draft_jobs=int(job_metrics_row.draft_jobs or 0),
            applications_awaiting_review=awaiting_rev,
            shortlisted_candidates=shortlisted,
            scheduled_interviews=interviews,
            hired_candidates=hired,
            pending_tasks=awaiting_rev,
        )

        # 5. Recruitment Funnel Aggregations
        # Calculated from actual pipeline stages
        funnel_counts: list[FunnelStageCount] = []
        funnel_definitions = [
            ("applied", "Applied", total_apps),
            (
                "review",
                "Resume Review",
                int(
                    (
                        await db.execute(
                            select(func.count(JobApplication.id))
                            .join(Job, JobApplication.job_id == Job.id)
                            .where(
                                and_(
                                    *app_filters,
                                    *job_filters,
                                    JobApplication.status.notin_(["withdrawn"]),
                                )
                            )
                        )
                    ).scalar()
                    or 0
                ),
            ),
            (
                "screening",
                "Screening",
                int(
                    (
                        await db.execute(
                            select(func.count(JobApplication.id))
                            .join(Job, JobApplication.job_id == Job.id)
                            .where(
                                and_(
                                    *app_filters,
                                    *job_filters,
                                    JobApplication.status.in_(
                                        [
                                            "in_screening",
                                            "screening",
                                            "shortlisted",
                                            "interview_stage",
                                            "interviewing",
                                            "offer_stage",
                                            "offer",
                                            "hired",
                                        ]
                                    ),
                                )
                            )
                        )
                    ).scalar()
                    or 0
                ),
            ),
            ("shortlisted", "Shortlisted", shortlisted + interviews + hired),
            ("interview", "Interview Round", interviews + hired),
            (
                "offer",
                "Offer Extended",
                int(
                    (
                        await db.execute(
                            select(func.count(JobApplication.id))
                            .join(Job, JobApplication.job_id == Job.id)
                            .where(
                                and_(
                                    *app_filters,
                                    *job_filters,
                                    JobApplication.status.in_(["offer_stage", "offer", "hired"]),
                                )
                            )
                        )
                    ).scalar()
                    or 0
                ),
            ),
            ("hired", "Hired", hired),
        ]

        for stage_key, label, count in funnel_definitions:
            pct = round((count / total_apps * 100.0), 1) if total_apps > 0 else 0.0
            funnel_counts.append(
                FunnelStageCount(stage=stage_key, label=label, count=count, percentage=pct)
            )

        # 6. Applications Over Time (Past 30 Days or Window)
        date_trunc_expr = func.to_char(JobApplication.applied_at, "YYYY-MM-DD")
        time_query = (
            select(date_trunc_expr.label("app_date"), func.count(JobApplication.id).label("count"))
            .join(Job, JobApplication.job_id == Job.id)
            .where(and_(*app_filters, *job_filters))
            .group_by("app_date")
            .order_by("app_date")
        )
        time_rows = (await db.execute(time_query)).all()
        over_time: list[ApplicationsOverTimePoint] = [
            ApplicationsOverTimePoint(date=r[0], applications_count=int(r[1])) for r in time_rows
        ]

        # 7. Applications by Job
        jobs_query = (
            select(
                Job.id,
                Job.title,
                Job.department,
                Job.status,
                func.count(JobApplication.id).label("total_apps"),
                func.count(
                    case(
                        (
                            JobApplication.status.in_(
                                ["submitted", "under_review", "shortlisted", "interviewing"]
                            ),
                            JobApplication.id,
                        )
                    )
                ).label("active_apps"),
            )
            .outerjoin(JobApplication, JobApplication.job_id == Job.id)
            .where(and_(*job_filters))
            .group_by(Job.id, Job.title, Job.department, Job.status)
            .order_by(desc("total_apps"))
            .limit(10)
        )
        job_rows = (await db.execute(jobs_query)).all()
        by_job: list[JobApplicationCount] = [
            JobApplicationCount(
                job_id=str(r[0]),
                job_title=r[1],
                department=r[2],
                status=r[3],
                applications_count=int(r[4] or 0),
                active_count=int(r[5] or 0),
            )
            for r in job_rows
        ]

        # 8. Applications by Department
        dept_query = (
            select(
                Job.department,
                func.count(JobApplication.id).label("dept_apps"),
                func.count(distinct(Job.id)).label("dept_jobs"),
            )
            .outerjoin(JobApplication, JobApplication.job_id == Job.id)
            .where(and_(*job_filters))
            .group_by(Job.department)
            .order_by(desc("dept_apps"))
            .limit(8)
        )
        dept_rows = (await db.execute(dept_query)).all()
        by_dept: list[DepartmentApplicationCount] = [
            DepartmentApplicationCount(
                department=r[0],
                applications_count=int(r[1] or 0),
                open_jobs_count=int(r[2] or 0),
            )
            for r in dept_rows
        ]

        # 9. Recent Applicants (Latest 5 with Eager Job & Candidate Profile)
        recent_apps_query = (
            select(JobApplication)
            .options(
                selectinload(JobApplication.job),
            )
            .join(Job, JobApplication.job_id == Job.id)
            .where(and_(*app_filters, *job_filters))
            .order_by(desc(JobApplication.applied_at))
            .limit(6)
        )
        recent_apps = (await db.execute(recent_apps_query)).scalars().all()

        recent_applicants: list[RecentApplicantItem] = []
        for app in recent_apps:
            # Fetch candidate user info
            user_res = await db.execute(
                select(User)
                .options(selectinload(User.candidate_profile))
                .where(User.id == app.candidate_id)
            )
            cand_user = user_res.scalar_one_or_none()
            full_name = "Candidate"
            email = "candidate@example.com"
            top_skills: list[str] = []

            if cand_user:
                email = cand_user.email
                first = cand_user.first_name or ""
                last = cand_user.last_name or ""
                full_name = f"{first} {last}".strip() or email.split("@")[0]
                if cand_user.candidate_profile and cand_user.candidate_profile.self_declared_skills:
                    top_skills = list(cand_user.candidate_profile.self_declared_skills)[:4]

            recent_applicants.append(
                RecentApplicantItem(
                    application_id=str(app.id),
                    candidate_id=str(app.candidate_id),
                    candidate_name=full_name,
                    candidate_email=email,
                    job_id=str(app.job_id),
                    job_title=app.job.title if app.job else "Requisition",
                    department=app.job.department if app.job else "General",
                    applied_at=app.applied_at.isoformat() if app.applied_at else now.isoformat(),
                    stage=app.status,
                    candidate_status=app.candidate_status,
                    resume_snapshot_sha256=app.resume_snapshot_sha256,
                    skills_count=len(top_skills),
                    top_skills=top_skills,
                )
            )

        # 10. Recent Recruitment Activities Feed (Derived from actual submissions and timeline)
        recent_activities: list[RecentActivityItem] = []
        for app in recent_apps[:5]:
            recent_activities.append(
                RecentActivityItem(
                    id=f"act-{app.id}",
                    event_type="application_submitted",
                    title="New Application Submitted",
                    description=f"Applied for {app.job.title if app.job else 'Position'}",
                    candidate_name=None,
                    job_title=app.job.title if app.job else None,
                    timestamp=app.applied_at.isoformat() if app.applied_at else now.isoformat(),
                    actor_name="Candidate",
                )
            )

        active_filters: dict[str, Any] = {}
        if start_date:
            active_filters["start_date"] = start_date.isoformat()
        if end_date:
            active_filters["end_date"] = end_date.isoformat()
        if department:
            active_filters["department"] = department
        if job_id:
            active_filters["job_id"] = str(job_id)
        if location:
            active_filters["location"] = location
        if employment_type:
            active_filters["employment_type"] = employment_type
        if stage:
            active_filters["stage"] = stage

        return HrDashboardOverviewResponse(
            tenant_id=str(tenant_id),
            organization_name=org_name,
            metrics=metrics,
            recruitment_funnel=funnel_counts,
            applications_over_time=over_time,
            applications_by_job=by_job,
            applications_by_department=by_dept,
            recent_applicants=recent_applicants,
            recent_activities=recent_activities,
            active_filters=active_filters,
        )


hr_dashboard_service = HrDashboardService()


class HrRequisitionService:
    """Service providing organization-isolated job requisition management."""

    def _normalize_skill_list(self, skills: list[str]) -> list[str]:
        """Normalize skills against Canonical Skill Registry while preserving custom competencies."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in skills:
            cleaned = raw.strip()
            if not cleaned:
                continue
            definition = skill_registry.resolve(cleaned)
            canon = definition.canonical_name if definition else cleaned
            if canon.lower() not in seen:
                seen.add(canon.lower())
                normalized.append(canon)
        return normalized

    def search_canonical_skills(
        self, query: str = "", limit: int = 15
    ) -> list[CanonicalSkillSuggestion]:
        """Search canonical skill taxonomy for autocomplete suggestions."""
        q = query.strip().lower()
        if not q:
            defs = skill_registry.all_definitions()[:limit]
            return [
                CanonicalSkillSuggestion(
                    canonical_name=d.canonical_name,
                    category=d.category,
                    skill_id=d.skill_id,
                )
                for d in defs
            ]
        results: list[CanonicalSkillSuggestion] = []
        for d in skill_registry.all_definitions():
            if q in d.canonical_name.lower() or any(q in alias.lower() for alias in d.aliases):
                results.append(
                    CanonicalSkillSuggestion(
                        canonical_name=d.canonical_name,
                        category=d.category,
                        skill_id=d.skill_id,
                    )
                )
                if len(results) >= limit:
                    break
        return results

    async def list_team_members(
        self, db: AsyncSession, tenant_id: UUID
    ) -> list[TeamMemberOption]:
        """List active organization members available for recruiter/hiring manager assignment."""
        stmt = (
            select(User, Role)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.is_active.is_(True),
            )
            .order_by(User.first_name, User.last_name)
        )
        res = await db.execute(stmt)
        members: list[TeamMemberOption] = []
        for user, role in res.all():
            name = f"{user.first_name} {user.last_name}".strip()
            members.append(
                TeamMemberOption(
                    id=user.id,
                    name=name,
                    email=user.email,
                    role=role.name,
                )
            )
        return members

    async def create_requisition(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        data: JobRequisitionCreate,
    ) -> JobRequisitionRead:
        """Create a new job requisition draft strictly bound to the authenticated tenant."""
        norm_required = self._normalize_skill_list(data.skills_required)
        norm_preferred = self._normalize_skill_list(data.preferred_skills)

        clean_slug = re.sub(r"[^a-z0-9]+", "-", data.title.lower()).strip("-")
        slug = f"{clean_slug}-{str(generate_uuid7())[:8]}"

        initial_status = data.status if data.status in ["draft", "pending_approval"] else "draft"

        job = Job(
            tenant_id=tenant_id,
            title=data.title.strip(),
            slug=slug,
            department=data.department.strip(),
            location=data.location.strip(),
            country=data.country.strip() if data.country else None,
            remote_type=data.remote_type,
            employment_type=data.employment_type,
            experience_level=data.experience_level,
            description=data.description,
            responsibilities=data.responsibilities,
            required_qualifications=data.required_qualifications,
            skills_required=norm_required,
            preferred_skills=norm_preferred,
            experience_requirements=data.experience_requirements,
            education_requirements=data.education_requirements,
            salary_min=data.salary_min,
            salary_max=data.salary_max,
            salary_currency=data.salary_currency.upper(),
            vacancies_count=data.vacancies_count,
            status=initial_status,
            approval_status=initial_status,
            visibility=data.visibility,
            application_deadline=data.application_deadline,
            recruiter_id=data.recruiter_id,
            hiring_manager_id=data.hiring_manager_id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        created = await self.get_requisition(db, tenant_id, job.id)
        if not created:
            raise AppException(message="Failed to retrieve created requisition", status_code=500)
        return created

    async def get_requisition(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
    ) -> JobRequisitionRead | None:
        """Fetch a specific job requisition scoped strictly to the organization."""
        stmt = (
            select(Job)
            .options(selectinload(Job.recruiter), selectinload(Job.hiring_manager))
            .where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return None

        app_count_res = await db.execute(
            select(func.count(JobApplication.id)).where(
                JobApplication.job_id == job.id,
                JobApplication.tenant_id == tenant_id,
            )
        )
        app_count = app_count_res.scalar_one() or 0

        return JobRequisitionRead(
            id=job.id,
            tenant_id=job.tenant_id,
            title=job.title,
            slug=job.slug,
            department=job.department,
            location=job.location,
            country=job.country,
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            experience_level=job.experience_level,
            description=job.description,
            responsibilities=job.responsibilities,
            required_qualifications=job.required_qualifications,
            requirements=job.requirements,
            skills_required=job.skills_required or [],
            preferred_skills=job.preferred_skills or [],
            experience_requirements=job.experience_requirements,
            education_requirements=job.education_requirements,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            vacancies_count=job.vacancies_count,
            status=job.status,
            approval_status=job.approval_status,
            visibility=job.visibility,
            recruiter_id=job.recruiter_id,
            recruiter_name=f"{job.recruiter.first_name} {job.recruiter.last_name}"
            if job.recruiter
            else None,
            recruiter_email=job.recruiter.email if job.recruiter else None,
            hiring_manager_id=job.hiring_manager_id,
            hiring_manager_name=f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}"
            if job.hiring_manager
            else None,
            hiring_manager_email=job.hiring_manager.email if job.hiring_manager else None,
            applications_count=app_count,
            published_at=job.published_at,
            application_deadline=job.application_deadline,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def list_requisitions(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        search: str | None = None,
        department: str | None = None,
        status: str | None = None,
        recruiter_id: UUID | None = None,
        hiring_manager_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> JobRequisitionListResponse:
        """List organization-scoped job requisitions with application counts and pagination."""
        base_filters = [Job.tenant_id == tenant_id]

        if search:
            s = f"%{search.strip()}%"
            base_filters.append(
                or_(
                    Job.title.ilike(s),
                    Job.department.ilike(s),
                    Job.location.ilike(s),
                )
            )
        if department:
            base_filters.append(Job.department == department)
        if status:
            base_filters.append(Job.status == status)
        if recruiter_id:
            base_filters.append(Job.recruiter_id == recruiter_id)
        if hiring_manager_id:
            base_filters.append(Job.hiring_manager_id == hiring_manager_id)

        count_stmt = select(func.count(Job.id)).where(*base_filters)
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one() or 0

        app_subq = (
            select(
                JobApplication.job_id,
                func.count(JobApplication.id).label("apps_count"),
            )
            .where(JobApplication.tenant_id == tenant_id)
            .group_by(JobApplication.job_id)
            .subquery()
        )

        order_col = Job.created_at
        if sort_by == "title":
            order_col = Job.title
        elif sort_by == "department":
            order_col = Job.department
        elif sort_by == "status":
            order_col = Job.status

        order_clause = desc(order_col) if sort_order.lower() == "desc" else order_col.asc()

        offset = (page - 1) * page_size
        query = (
            select(Job, func.coalesce(app_subq.c.apps_count, 0).label("app_count"))
            .outerjoin(app_subq, app_subq.c.job_id == Job.id)
            .options(selectinload(Job.recruiter), selectinload(Job.hiring_manager))
            .where(*base_filters)
            .order_by(order_clause)
            .offset(offset)
            .limit(page_size)
        )

        results = await db.execute(query)
        items: list[JobRequisitionRead] = []
        for job, count in results.all():
            items.append(
                JobRequisitionRead(
                    id=job.id,
                    tenant_id=job.tenant_id,
                    title=job.title,
                    slug=job.slug,
                    department=job.department,
                    location=job.location,
                    country=job.country,
                    remote_type=job.remote_type,
                    employment_type=job.employment_type,
                    experience_level=job.experience_level,
                    description=job.description,
                    responsibilities=job.responsibilities,
                    required_qualifications=job.required_qualifications,
                    requirements=job.requirements,
                    skills_required=job.skills_required or [],
                    preferred_skills=job.preferred_skills or [],
                    experience_requirements=job.experience_requirements,
                    education_requirements=job.education_requirements,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    salary_currency=job.salary_currency,
                    vacancies_count=job.vacancies_count,
                    status=job.status,
                    approval_status=job.approval_status,
                    visibility=job.visibility,
                    recruiter_id=job.recruiter_id,
                    recruiter_name=f"{job.recruiter.first_name} {job.recruiter.last_name}"
                    if job.recruiter
                    else None,
                    recruiter_email=job.recruiter.email if job.recruiter else None,
                    hiring_manager_id=job.hiring_manager_id,
                    hiring_manager_name=f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}"
                    if job.hiring_manager
                    else None,
                    hiring_manager_email=job.hiring_manager.email
                    if job.hiring_manager
                    else None,
                    applications_count=count,
                    published_at=job.published_at,
                    application_deadline=job.application_deadline,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )

        pages = (total + page_size - 1) // page_size if total > 0 else 1
        return JobRequisitionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def update_requisition(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
        data: JobRequisitionUpdate,
    ) -> JobRequisitionRead | None:
        """Update job requisition details strictly within the tenant boundary."""
        stmt = select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return None

        update_dict = data.model_dump(exclude_unset=True)
        if "skills_required" in update_dict and update_dict["skills_required"] is not None:
            update_dict["skills_required"] = self._normalize_skill_list(
                update_dict["skills_required"]
            )
        if "preferred_skills" in update_dict and update_dict["preferred_skills"] is not None:
            update_dict["preferred_skills"] = self._normalize_skill_list(
                update_dict["preferred_skills"]
            )

        for field, val in update_dict.items():
            setattr(job, field, val)

        await db.commit()
        return await self.get_requisition(db, tenant_id, job.id)

    async def delete_requisition(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
    ) -> bool:
        """Safely delete draft job requisition if no candidate applications exist."""
        stmt = select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return False

        app_count_res = await db.execute(
            select(func.count(JobApplication.id)).where(
                JobApplication.job_id == job.id,
                JobApplication.tenant_id == tenant_id,
            )
        )
        if (app_count_res.scalar_one() or 0) > 0:
            raise ConflictException(
                message="Cannot delete job requisition with existing candidate applications. Archive or close it instead."
            )

        await db.delete(job)
        await db.commit()
        return True


hr_requisition_service = HrRequisitionService()
