"""HR Dashboard service orchestrating organization-scoped recruitment metrics and analytics.

Conforms strictly to Step 4.2 multi-tenant isolation specifications.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import utc_now
from app.modules.auth.models import User
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
from app.modules.organizations.models import Organization

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
