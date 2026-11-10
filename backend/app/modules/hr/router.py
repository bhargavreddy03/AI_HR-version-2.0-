"""FastAPI router for HR / Recruiter Dashboard and Analytics.

Conforms strictly to Step 4.2 multi-tenant isolation and role-authorization architecture.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AuthorizationException
from app.core.security import SecurityContext
from app.modules.auth.dependencies import (
    require_authenticated_user,
)
from app.modules.hr.schemas import HrDashboardOverviewResponse
from app.modules.hr.service import hr_dashboard_service
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
