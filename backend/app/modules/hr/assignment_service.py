"""Recruiter and Hiring Manager Assignment Service.

Enforces organization membership validation, strict role distinctions, immutable assignment history,
idempotent notification dispatch, and real-time database-driven team workload metrics.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AuthorizationException,
    EntityNotFoundException,
    ValidationException,
)
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateNotification
from app.modules.hr.assignment_schemas import (
    AssignedVacanciesResponse,
    AssignedVacancyItem,
    JobAssignmentHistoryItem,
    JobAssignmentUpdateResponse,
    TeamWorkloadResponse,
    TeamWorkloadSummary,
    UserWorkloadItem,
)
from app.modules.jobs.models import (
    Job,
    JobApplication,
    JobAssignmentHistory,
)
from app.modules.notifications.tasks import dispatch_candidate_email_notification
from app.modules.organizations.models import OrganizationMembership, Role

logger = logging.getLogger(__name__)

# Permitted roles for assignment targets
VALID_RECRUITER_ROLES = {"recruiter", "admin", "org_admin", "platform_super_admin"}
VALID_HIRING_MANAGER_ROLES = {"hiring_manager", "admin", "org_admin", "platform_super_admin"}


class HrAssignmentService:
    """Service orchestrating recruitment assignments, authorization, workload, and notifications."""

    async def _verify_actor_permission(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job: Job,
        actor_id: UUID,
        actor_roles: list[str],
        is_super_admin: bool,
    ) -> str:
        """Verify actor has authority to modify job assignments.

        Returns actor's display name.
        """
        # Platform Super Admins and Org Admins always have authority
        admin_roles = {"admin", "org_admin", "platform_super_admin"}
        if is_super_admin or set(actor_roles).intersection(admin_roles):
            actor_user = await db.get(User, actor_id)
            if actor_user:
                return f"{actor_user.first_name} {actor_user.last_name}".strip()
            return "Organization Admin"

        # Check if caller is the assigned recruiter or hiring manager on this specific job
        if job.recruiter_id == actor_id or job.hiring_manager_id == actor_id:
            actor_user = await db.get(User, actor_id)
            if actor_user:
                return f"{actor_user.first_name} {actor_user.last_name}".strip()
            return "Assigned Team Member"

        # Check database membership role if token claims role was not populated
        stmt = (
            select(OrganizationMembership, Role, User)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == actor_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        res = await db.execute(stmt)
        record = res.first()
        if not record:
            raise AuthorizationException(
                "Active organization membership required to modify assignments.",
                code="ASSIGNMENT_UNAUTHORIZED",
            )

        _, role, user = record
        if role.name in admin_roles:
            return f"{user.first_name} {user.last_name}".strip()

        raise AuthorizationException(
            "Only Organization Admins or the assigned team members may modify job recruitment assignments.",
            code="ASSIGNMENT_UNAUTHORIZED",
        )

    async def _validate_assignment_target(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        target_user_id: UUID | None,
        assignment_type: str,
    ) -> tuple[User | None, str | None]:
        """Validate that the target user is an active member with the correct role."""
        if target_user_id is None:
            return None, None

        stmt = (
            select(User, Role)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == target_user_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        res = await db.execute(stmt)
        row = res.first()

        if not row:
            raise ValidationException(
                f"Selected {assignment_type} is not an active member of this organization.",
                code="USER_NOT_ORGANIZATION_MEMBER",
            )

        user, role = row
        allowed_roles = (
            VALID_RECRUITER_ROLES if assignment_type == "recruiter" else VALID_HIRING_MANAGER_ROLES
        )

        if role.name not in allowed_roles:
            raise ValidationException(
                f"User '{user.email}' possesses role '{role.name}', which is not authorized for {assignment_type} assignment.",
                code=f"INVALID_{assignment_type.upper()}_ROLE",
            )

        name = f"{user.first_name} {user.last_name}".strip()
        return user, name

    async def _send_assignment_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        user_email: str,
        title: str,
        message: str,
        event_type: str,
        job_id: UUID,
        action_url: str,
    ) -> None:
        """Create in-app notification and trigger idempotent background notification dispatch."""
        notif = CandidateNotification(
            id=generate_uuid7(),
            user_id=user_id,
            title=title,
            message=message,
            category="assignment_alert",
            event_type=event_type,
            action_url=action_url,
            payload={"job_id": str(job_id), "event_type": event_type},
        )
        db.add(notif)

        # Dispatch email delivery idempotently
        try:
            dispatch_candidate_email_notification(
                notification_id=str(notif.id),
                recipient_email=user_email,
                subject=title,
                body=message,
                idempotency_key=f"assignment:{job_id}:{event_type}:{user_id}",
            )
        except Exception as exc:
            logger.info("Email notification dispatch skipped: %s", exc)

    async def assign_recruiter(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
        recruiter_id: UUID | None,
        actor_id: UUID,
        actor_roles: list[str],
        is_super_admin: bool = False,
        reason: str | None = None,
    ) -> JobAssignmentUpdateResponse:
        """Assign, change, or remove lead recruiter for a job."""
        job = await db.get(Job, job_id)
        if not job or job.tenant_id != tenant_id:
            raise EntityNotFoundException("Job requisition", job_id)

        actor_name = await self._verify_actor_permission(
            db=db,
            tenant_id=tenant_id,
            job=job,
            actor_id=actor_id,
            actor_roles=actor_roles,
            is_super_admin=is_super_admin,
        )

        # Validate target recruiter
        new_user, new_name = await self._validate_assignment_target(
            db=db, tenant_id=tenant_id, target_user_id=recruiter_id, assignment_type="recruiter"
        )

        previous_user_id = job.recruiter_id
        previous_user = await db.get(User, previous_user_id) if previous_user_id else None
        previous_name = (
            f"{previous_user.first_name} {previous_user.last_name}".strip()
            if previous_user
            else None
        )

        # Skip if identical
        if previous_user_id == recruiter_id:
            return JobAssignmentUpdateResponse(
                job_id=job.id,
                job_title=job.title,
                recruiter_id=job.recruiter_id,
                recruiter_name=new_name or previous_name,
                hiring_manager_id=job.hiring_manager_id,
                hiring_manager_name=f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}".strip()
                if job.hiring_manager
                else None,
                updated_at=job.updated_at,
                message="Recruiter assignment remains unchanged.",
            )

        # Update job
        job.recruiter_id = recruiter_id
        job.updated_at = utc_now()

        # Record assignment history
        history_entry = JobAssignmentHistory(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            job_id=job.id,
            assignment_type="recruiter",
            actor_id=actor_id,
            actor_name=actor_name,
            previous_user_id=previous_user_id,
            previous_user_name=previous_name,
            new_user_id=recruiter_id,
            new_user_name=new_name,
            reason=reason,
            created_at=utc_now(),
        )
        db.add(history_entry)

        # Notifications
        if new_user:
            await self._send_assignment_notification(
                db=db,
                user_id=new_user.id,
                user_email=new_user.email,
                title="Assigned as Lead Recruiter",
                message=f"You have been assigned to lead recruitment for '{job.title}' ({job.department}).",
                event_type="job_recruiter_assigned",
                job_id=job.id,
                action_url=f"/hr/jobs/{job.id}",
            )

        if previous_user and previous_user.id != recruiter_id:
            await self._send_assignment_notification(
                db=db,
                user_id=previous_user.id,
                user_email=previous_user.email,
                title="Unassigned from Job Requisition",
                message=f"You are no longer assigned as lead recruiter for '{job.title}'. Note: {reason or 'Assignment updated'}",
                event_type="job_recruiter_unassigned",
                job_id=job.id,
                action_url=f"/hr/jobs/{job.id}",
            )

        await db.commit()

        # Re-fetch HM name if set
        hm_name = None
        if job.hiring_manager_id:
            hm_user = await db.get(User, job.hiring_manager_id)
            if hm_user:
                hm_name = f"{hm_user.first_name} {hm_user.last_name}".strip()

        return JobAssignmentUpdateResponse(
            job_id=job.id,
            job_title=job.title,
            recruiter_id=job.recruiter_id,
            recruiter_name=new_name,
            hiring_manager_id=job.hiring_manager_id,
            hiring_manager_name=hm_name,
            updated_at=job.updated_at,
            message=f"Recruiter assignment successfully updated to {new_name or 'Unassigned'}.",
        )

    async def assign_hiring_manager(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        job_id: UUID,
        hiring_manager_id: UUID | None,
        actor_id: UUID,
        actor_roles: list[str],
        is_super_admin: bool = False,
        reason: str | None = None,
    ) -> JobAssignmentUpdateResponse:
        """Assign, change, or remove hiring manager for a job."""
        job = await db.get(Job, job_id)
        if not job or job.tenant_id != tenant_id:
            raise EntityNotFoundException("Job requisition", job_id)

        actor_name = await self._verify_actor_permission(
            db=db,
            tenant_id=tenant_id,
            job=job,
            actor_id=actor_id,
            actor_roles=actor_roles,
            is_super_admin=is_super_admin,
        )

        # Validate target hiring manager
        new_user, new_name = await self._validate_assignment_target(
            db=db,
            tenant_id=tenant_id,
            target_user_id=hiring_manager_id,
            assignment_type="hiring_manager",
        )

        previous_user_id = job.hiring_manager_id
        previous_user = await db.get(User, previous_user_id) if previous_user_id else None
        previous_name = (
            f"{previous_user.first_name} {previous_user.last_name}".strip()
            if previous_user
            else None
        )

        if previous_user_id == hiring_manager_id:
            recruiter_name = None
            if job.recruiter_id:
                rec_user = await db.get(User, job.recruiter_id)
                if rec_user:
                    recruiter_name = f"{rec_user.first_name} {rec_user.last_name}".strip()

            return JobAssignmentUpdateResponse(
                job_id=job.id,
                job_title=job.title,
                recruiter_id=job.recruiter_id,
                recruiter_name=recruiter_name,
                hiring_manager_id=job.hiring_manager_id,
                hiring_manager_name=new_name or previous_name,
                updated_at=job.updated_at,
                message="Hiring manager assignment remains unchanged.",
            )

        # Update job
        job.hiring_manager_id = hiring_manager_id
        job.updated_at = utc_now()

        # Record assignment history
        history_entry = JobAssignmentHistory(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            job_id=job.id,
            assignment_type="hiring_manager",
            actor_id=actor_id,
            actor_name=actor_name,
            previous_user_id=previous_user_id,
            previous_user_name=previous_name,
            new_user_id=hiring_manager_id,
            new_user_name=new_name,
            reason=reason,
            created_at=utc_now(),
        )
        db.add(history_entry)

        # Notifications
        if new_user:
            await self._send_assignment_notification(
                db=db,
                user_id=new_user.id,
                user_email=new_user.email,
                title="Assigned as Hiring Manager",
                message=f"You have been assigned as Hiring Manager for '{job.title}' ({job.department}). You now have review authority for applicants.",
                event_type="job_hiring_manager_assigned",
                job_id=job.id,
                action_url=f"/hr/jobs/{job.id}",
            )

        if previous_user and previous_user.id != hiring_manager_id:
            await self._send_assignment_notification(
                db=db,
                user_id=previous_user.id,
                user_email=previous_user.email,
                title="Unassigned as Hiring Manager",
                message=f"You are no longer assigned as Hiring Manager for '{job.title}'. Note: {reason or 'Assignment updated'}",
                event_type="job_hiring_manager_unassigned",
                job_id=job.id,
                action_url=f"/hr/jobs/{job.id}",
            )

        await db.commit()

        # Re-fetch Recruiter name if set
        rec_name = None
        if job.recruiter_id:
            rec_user = await db.get(User, job.recruiter_id)
            if rec_user:
                rec_name = f"{rec_user.first_name} {rec_user.last_name}".strip()

        return JobAssignmentUpdateResponse(
            job_id=job.id,
            job_title=job.title,
            recruiter_id=job.recruiter_id,
            recruiter_name=rec_name,
            hiring_manager_id=job.hiring_manager_id,
            hiring_manager_name=new_name,
            updated_at=job.updated_at,
            message=f"Hiring manager assignment successfully updated to {new_name or 'Unassigned'}.",
        )

    async def get_job_assignment_history(
        self, db: AsyncSession, tenant_id: UUID, job_id: UUID
    ) -> list[JobAssignmentHistoryItem]:
        """Retrieve complete immutable chronological audit trail of assignment changes."""
        job = await db.get(Job, job_id)
        if not job or job.tenant_id != tenant_id:
            raise EntityNotFoundException("Job requisition", job_id)

        stmt = (
            select(JobAssignmentHistory)
            .where(
                JobAssignmentHistory.tenant_id == tenant_id,
                JobAssignmentHistory.job_id == job_id,
            )
            .order_by(desc(JobAssignmentHistory.created_at))
        )
        res = await db.execute(stmt)
        entries = res.scalars().all()

        return [
            JobAssignmentHistoryItem(
                id=entry.id,
                job_id=entry.job_id,
                assignment_type=entry.assignment_type,
                actor_id=entry.actor_id,
                actor_name=entry.actor_name,
                previous_user_id=entry.previous_user_id,
                previous_user_name=entry.previous_user_name,
                new_user_id=entry.new_user_id,
                new_user_name=entry.new_user_name,
                reason=entry.reason,
                created_at=entry.created_at,
            )
            for entry in entries
        ]

    async def get_team_workload(
        self, db: AsyncSession, tenant_id: UUID
    ) -> TeamWorkloadResponse:
        """Compute live database-driven recruitment workload metrics across recruiters and hiring managers."""
        # 1. Fetch all active organization members with roles
        stmt = (
            select(User, Role, OrganizationMembership)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.is_active.is_(True),
            )
            .order_by(User.first_name, User.last_name)
        )
        res = await db.execute(stmt)
        members = res.all()

        # 2. Fetch all jobs in tenant
        jobs_stmt = select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status != "archived",
        )
        jobs_res = await db.execute(jobs_stmt)
        all_jobs = jobs_res.scalars().all()

        # 3. Fetch applications grouped by job
        apps_stmt = select(
            JobApplication.job_id,
            JobApplication.status,
            func.count(JobApplication.id).label("count"),
        ).where(
            JobApplication.tenant_id == tenant_id,
            JobApplication.status != "withdrawn",
        ).group_by(JobApplication.job_id, JobApplication.status)
        apps_res = await db.execute(apps_stmt)
        job_apps_data = apps_res.all()

        # Index applications counts by job_id
        # { job_id: { "total": x, "pending": y, "interview": z } }
        job_stats: dict[UUID, dict[str, int]] = {}
        pending_stages = {"applied", "resume_review", "screening", "submitted", "in_screening", "under_review"}
        interview_stages = {"interview", "final_interview", "interview_stage", "interviewing"}

        for j_id, stage, count in job_apps_data:
            if j_id not in job_stats:
                job_stats[j_id] = {"total": 0, "pending": 0, "interview": 0}
            job_stats[j_id]["total"] += count
            if stage in pending_stages:
                job_stats[j_id]["pending"] += count
            if stage in interview_stages:
                job_stats[j_id]["interview"] += count

        # 4. Map user workloads
        recruiters_list: list[UserWorkloadItem] = []
        hiring_managers_list: list[UserWorkloadItem] = []

        total_active_apps = sum(s["total"] for s in job_stats.values())
        assigned_job_ids = set()

        for user, role, mem in members:
            # Match assigned jobs
            is_recruiter = role.name in VALID_RECRUITER_ROLES
            is_hiring_manager = role.name in VALID_HIRING_MANAGER_ROLES

            # Compute assigned jobs
            assigned_as_recruiter = [j for j in all_jobs if j.recruiter_id == user.id]
            assigned_as_hm = [j for j in all_jobs if j.hiring_manager_id == user.id]

            if is_recruiter:
                assigned = assigned_as_recruiter
                assigned_job_ids.update(j.id for j in assigned)
                active_jobs = [j for j in assigned if j.status in ("published", "draft", "pending_approval", "paused")]
                total_apps = sum(job_stats.get(j.id, {}).get("total", 0) for j in assigned)
                pending_revs = sum(job_stats.get(j.id, {}).get("pending", 0) for j in assigned)
                active_ints = sum(job_stats.get(j.id, {}).get("interview", 0) for j in assigned)

                # Capacity status
                if pending_revs >= 15 or len(active_jobs) >= 8:
                    status = "critical"
                elif pending_revs >= 8 or len(active_jobs) >= 5:
                    status = "high"
                elif len(active_jobs) >= 1:
                    status = "balanced"
                else:
                    status = "low"

                recruiters_list.append(
                    UserWorkloadItem(
                        user_id=user.id,
                        name=f"{user.first_name} {user.last_name}".strip(),
                        email=user.email,
                        role=role.name,
                        department_id=mem.department_id,
                        assigned_jobs_count=len(assigned),
                        active_jobs_count=len(active_jobs),
                        total_applications_count=total_apps,
                        pending_reviews_count=pending_revs,
                        active_interviews_count=active_ints,
                        workload_status=status,
                    )
                )

            if is_hiring_manager and role.name != "recruiter":
                assigned = assigned_as_hm
                assigned_job_ids.update(j.id for j in assigned)
                active_jobs = [j for j in assigned if j.status in ("published", "draft", "pending_approval", "paused")]
                total_apps = sum(job_stats.get(j.id, {}).get("total", 0) for j in assigned)
                pending_revs = sum(job_stats.get(j.id, {}).get("pending", 0) for j in assigned)
                active_ints = sum(job_stats.get(j.id, {}).get("interview", 0) for j in assigned)

                if pending_revs >= 15 or len(active_jobs) >= 8:
                    status = "critical"
                elif pending_revs >= 8 or len(active_jobs) >= 5:
                    status = "high"
                elif len(active_jobs) >= 1:
                    status = "balanced"
                else:
                    status = "low"

                hiring_managers_list.append(
                    UserWorkloadItem(
                        user_id=user.id,
                        name=f"{user.first_name} {user.last_name}".strip(),
                        email=user.email,
                        role=role.name,
                        department_id=mem.department_id,
                        assigned_jobs_count=len(assigned),
                        active_jobs_count=len(active_jobs),
                        total_applications_count=total_apps,
                        pending_reviews_count=pending_revs,
                        active_interviews_count=active_ints,
                        workload_status=status,
                    )
                )

        unassigned_count = len([j for j in all_jobs if not j.recruiter_id and not j.hiring_manager_id])

        summary = TeamWorkloadSummary(
            total_team_members=len(members),
            total_assigned_jobs=len(all_jobs) - unassigned_count,
            total_unassigned_jobs=unassigned_count,
            total_active_applications=total_active_apps,
        )

        return TeamWorkloadResponse(
            tenant_id=tenant_id,
            recruiters=recruiters_list,
            hiring_managers=hiring_managers_list,
            summary=summary,
        )

    async def get_assigned_vacancies(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID
    ) -> AssignedVacanciesResponse:
        """Retrieve vacancies assigned to the requesting user as lead recruiter or hiring manager."""
        stmt = (
            select(Job)
            .options(
                selectinload(Job.recruiter),
                selectinload(Job.hiring_manager),
                selectinload(Job.applications),
            )
            .where(
                Job.tenant_id == tenant_id,
                Job.status != "archived",
                or_(Job.recruiter_id == user_id, Job.hiring_manager_id == user_id),
            )
            .order_by(desc(Job.created_at))
        )
        res = await db.execute(stmt)
        jobs = res.scalars().all()

        pending_stages = {"applied", "resume_review", "screening", "submitted", "in_screening", "under_review"}
        interview_stages = {"interview", "final_interview", "interview_stage", "interviewing"}

        items: list[AssignedVacancyItem] = []
        for job in jobs:
            active_apps = [a for a in job.applications if a.status != "withdrawn"]
            pending_count = len([a for a in active_apps if a.status in pending_stages])
            interview_count = len([a for a in active_apps if a.status in interview_stages])

            items.append(
                AssignedVacancyItem(
                    id=job.id,
                    title=job.title,
                    department=job.department,
                    status=job.status,
                    work_arrangement=getattr(job, "remote_type", "remote") or "remote",
                    vacancies=job.vacancies_count if hasattr(job, "vacancies_count") else 1,
                    active_applications_count=len(active_apps),
                    pending_reviews_count=pending_count,
                    scheduled_interviews_count=interview_count,
                    recruiter_id=job.recruiter_id,
                    recruiter_name=f"{job.recruiter.first_name} {job.recruiter.last_name}".strip()
                    if job.recruiter
                    else None,
                    hiring_manager_id=job.hiring_manager_id,
                    hiring_manager_name=f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}".strip()
                    if job.hiring_manager
                    else None,
                    created_at=job.created_at,
                )
            )

        return AssignedVacanciesResponse(
            tenant_id=tenant_id,
            vacancies=items,
            total=len(items),
        )


# Global singleton instance
hr_assignment_service = HrAssignmentService()
