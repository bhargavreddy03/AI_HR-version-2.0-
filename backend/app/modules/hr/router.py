"""FastAPI router for HR / Recruiter Dashboard and Analytics.

Conforms strictly to Step 4.2 multi-tenant isolation and role-authorization architecture.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AuthorizationException, EntityNotFoundException
from app.core.security import SecurityContext
from app.modules.auth.dependencies import (
    require_authenticated_user,
)
from app.modules.hr.lifecycle_schemas import (
    JobLifecycleActionRequest,
    JobLifecycleHistoryItem,
    JobLifecyclePermittedActionsResponse,
    JobLifecycleTransitionResponse,
)
from app.modules.hr.lifecycle_service import hr_job_lifecycle_service
from app.modules.hr.requisition_schemas import (
    CanonicalSkillSuggestion,
    JobRequisitionCreate,
    JobRequisitionListResponse,
    JobRequisitionRead,
    JobRequisitionUpdate,
    TeamMemberOption,
)
from app.modules.hr.schemas import HrDashboardOverviewResponse
from app.modules.hr.service import hr_dashboard_service, hr_requisition_service
from app.modules.organizations.models import OrganizationMembership

logger = logging.getLogger(__name__)

hr_router = APIRouter(prefix="/hr", tags=["HR & Recruiter Portal"])


async def resolve_hr_tenant_context(
    request: Request,
    sec: SecurityContext = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Resolve and enforce active tenant organization boundary for HR operations.

    Rejects requests without valid active organization membership or unauthorized candidate users.
    """
    tenant_id = sec.tenant_id

    # If tenant_id was not baked into token claims, resolve user's active membership
    if not tenant_id:
        mem_res = await db.execute(
            select(OrganizationMembership.tenant_id).where(
                OrganizationMembership.user_id == sec.user_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        tenant_id = mem_res.scalar_one_or_none()

    if not tenant_id:
        raise AuthorizationException(
            "An active organization membership is required to access the HR Recruiter portal.",
            error_code="HR_TENANT_MEMBERSHIP_REQUIRED",
        )

    # Verify user possesses recruiter, hiring manager, org admin, or super admin capability
    authorized_roles = {"recruiter", "hiring_manager", "org_admin", "platform_super_admin", "admin"}
    user_roles = set(sec.roles)
    if not (user_roles.intersection(authorized_roles) or sec.is_super_admin):
        # Check database membership role if token claims role was not populated
        role_res = await db.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == sec.user_id,
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        if not role_res.scalar_one_or_none():
            raise AuthorizationException(
                "You do not possess authorized recruiter or hiring team permissions for this organization.",
                error_code="HR_ACCESS_FORBIDDEN",
            )

    return tenant_id


@hr_router.get(
    "/dashboard/overview",
    response_model=HrDashboardOverviewResponse,
    summary="Retrieve organization-scoped recruitment dashboard metrics and charts",
)
async def get_dashboard_overview(
    start_date: datetime | None = Query(None, description="Start date filter (ISO-8601)"),
    end_date: datetime | None = Query(None, description="End date filter (ISO-8601)"),
    department: str | None = Query(None, description="Filter by department"),
    job_id: UUID | None = Query(None, description="Filter by job requisition UUID"),
    location: str | None = Query(None, description="Filter by location keyword"),
    employment_type: str | None = Query(None, description="Filter by employment type"),
    stage: str | None = Query(None, description="Filter by application stage"),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> HrDashboardOverviewResponse:
    """Provide real organization-isolated recruitment KPI aggregations, funnel, and trends."""
    return await hr_dashboard_service.get_dashboard_overview(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        department=department,
        job_id=job_id,
        location=location,
        employment_type=employment_type,
        stage=stage,
    )


# ------------------------------------------------------------------------------
# Job Requisition Endpoints (Step 4.2.3)
# ------------------------------------------------------------------------------


@hr_router.get(
    "/jobs",
    response_model=JobRequisitionListResponse,
    summary="List organization-scoped job requisitions with pagination and filters",
)
async def list_requisitions(
    search: str | None = Query(None, description="Search by title, department, or location"),
    department: str | None = Query(None, description="Filter by department"),
    status: str | None = Query(None, description="Filter by status (draft, published, etc.)"),
    recruiter_id: UUID | None = Query(None, description="Filter by recruiter UUID"),
    hiring_manager_id: UUID | None = Query(None, description="Filter by hiring manager UUID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Field to sort by (created_at, title, department, status)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobRequisitionListResponse:
    """List job requisitions strictly within the caller's organization boundary."""
    return await hr_requisition_service.list_requisitions(
        db=db,
        tenant_id=tenant_id,
        search=search,
        department=department,
        status=status,
        recruiter_id=recruiter_id,
        hiring_manager_id=hiring_manager_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@hr_router.post(
    "/jobs",
    response_model=JobRequisitionRead,
    status_code=201,
    summary="Create a new job requisition draft or pending approval",
)
async def create_requisition(
    data: JobRequisitionCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobRequisitionRead:
    """Create a new job requisition bound strictly to the caller's organization."""
    return await hr_requisition_service.create_requisition(
        db=db,
        tenant_id=tenant_id,
        data=data,
    )


@hr_router.get(
    "/jobs/team-members",
    response_model=list[TeamMemberOption],
    summary="Retrieve organization members available for recruiter or hiring manager assignment",
)
async def list_team_members(
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> list[TeamMemberOption]:
    """Retrieve active organization members available for assignment."""
    return await hr_requisition_service.list_team_members(db=db, tenant_id=tenant_id)


@hr_router.get(
    "/jobs/skills-autocomplete",
    response_model=list[CanonicalSkillSuggestion],
    summary="Search canonical technical skills taxonomy for requisition autocompletion",
)
async def autocomplete_canonical_skills(
    q: str = Query("", description="Skill keyword search query"),
    limit: int = Query(15, ge=1, le=50, description="Max suggestions to return"),
    _: UUID = Depends(resolve_hr_tenant_context),
) -> list[CanonicalSkillSuggestion]:
    """Provide verified canonical skill autocomplete suggestions."""
    return hr_requisition_service.search_canonical_skills(query=q, limit=limit)


@hr_router.get(
    "/jobs/{job_id}",
    response_model=JobRequisitionRead,
    summary="Retrieve detailed job requisition information",
)
async def get_requisition(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobRequisitionRead:
    """Fetch complete requisition record scoped to tenant."""
    requisition = await hr_requisition_service.get_requisition(
        db=db, tenant_id=tenant_id, job_id=job_id
    )
    if not requisition:
        raise EntityNotFoundException("JobRequisition", job_id)
    return requisition


@hr_router.put(
    "/jobs/{job_id}",
    response_model=JobRequisitionRead,
    summary="Update an existing job requisition",
)
async def update_requisition(
    job_id: UUID,
    data: JobRequisitionUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobRequisitionRead:
    """Update job requisition details within tenant boundary."""
    updated = await hr_requisition_service.update_requisition(
        db=db, tenant_id=tenant_id, job_id=job_id, data=data
    )
    if not updated:
        raise EntityNotFoundException("JobRequisition", job_id)
    return updated


@hr_router.delete(
    "/jobs/{job_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a draft job requisition without applications",
)
async def delete_requisition(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> Response:
    """Safely delete draft job requisition if no candidate applications exist."""
    deleted = await hr_requisition_service.delete_requisition(
        db=db, tenant_id=tenant_id, job_id=job_id
    )
    if not deleted:
        raise EntityNotFoundException("JobRequisition", job_id)
    return Response(status_code=204)


# ------------------------------------------------------------------------------
# Job Publication & Lifecycle Endpoints (Step 4.2.4)
# ------------------------------------------------------------------------------


@hr_router.post(
    "/jobs/{job_id}/lifecycle",
    response_model=JobLifecycleTransitionResponse,
    summary="Execute a job requisition lifecycle state transition action",
)
async def execute_job_lifecycle_action(
    job_id: UUID,
    request: JobLifecycleActionRequest,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobLifecycleTransitionResponse:
    """Execute FSM state transition (submit, approve, request changes, publish, pause, reopen, close, archive)."""
    return await hr_job_lifecycle_service.execute_transition(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        user_id=sec.user_id,
        user_roles=sec.roles,
        request=request,
        is_super_admin=sec.is_super_admin,
    )


@hr_router.get(
    "/jobs/{job_id}/lifecycle/history",
    response_model=list[JobLifecycleHistoryItem],
    summary="Retrieve immutable lifecycle audit history for a job requisition",
)
async def get_job_lifecycle_history(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> list[JobLifecycleHistoryItem]:
    """Retrieve immutable chronological audit trail of all lifecycle state transitions."""
    return await hr_job_lifecycle_service.get_history(
        db=db, tenant_id=tenant_id, job_id=job_id
    )


@hr_router.get(
    "/jobs/{job_id}/lifecycle/permitted-actions",
    response_model=JobLifecyclePermittedActionsResponse,
    summary="Evaluate permitted lifecycle actions for current user and check separation of duties",
)
async def get_permitted_lifecycle_actions(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
    tenant_id: UUID = Depends(resolve_hr_tenant_context),
) -> JobLifecyclePermittedActionsResponse:
    """Evaluate authorized actions for the calling user including separation of duties check."""
    return await hr_job_lifecycle_service.evaluate_permitted_actions(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        user_id=sec.user_id,
        user_roles=sec.roles,
        is_super_admin=sec.is_super_admin,
    )
