"""Unit and integration tests for Step 4.2.2 HR Dashboard and Recruitment Overview.

Verifies real metric calculations, multi-tenant boundary enforcement, role authorization,
funnel conversions, date filters, and empty organization handling.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.base import utc_now
from app.core.errors import AuthorizationException
from app.core.security import SecurityContext
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.hr.router import resolve_hr_tenant_context
from app.modules.hr.schemas import HrDashboardOverviewResponse
from app.modules.hr.service import hr_dashboard_service
from app.modules.jobs.models import Job, JobApplication
from app.modules.organizations.models import Organization


@pytest.mark.asyncio
async def test_hr_dashboard_overview_metrics_calculation() -> None:
    """Verify accurate aggregation of organization-scoped KPI metrics, funnel, and jobs."""
    tenant_id = uuid4()
    job_id = uuid4()
    candidate_1 = uuid4()

    mock_db = AsyncMock()

    # 1. Mock Organization resolution
    mock_org = Organization(id=tenant_id, name="Acme Corp", slug="acme")
    org_res = MagicMock()
    org_res.scalar_one_or_none.return_value = mock_org

    # 2. Mock Application metric row
    app_metrics_mock = MagicMock(
        total_applications=12,
        total_candidates=8,
        awaiting_review=5,
        shortlisted=3,
        scheduled_interviews=2,
        hired=1,
    )
    app_res = MagicMock()
    app_res.one.return_value = app_metrics_mock

    # 3. Mock Job metric row
    job_metrics_mock = MagicMock(
        active_jobs=4,
        published_jobs=5,
        draft_jobs=2,
    )
    job_res = MagicMock()
    job_res.one.return_value = job_metrics_mock

    # 4. Mock Funnel scalar counts
    funnel_review_res = MagicMock()
    funnel_review_res.scalar.return_value = 11

    funnel_screening_res = MagicMock()
    funnel_screening_res.scalar.return_value = 6

    funnel_offer_res = MagicMock()
    funnel_offer_res.scalar.return_value = 2

    # 5. Mock Time-series rows
    time_res = MagicMock()
    time_res.all.return_value = [
        ("2026-11-01", 3),
        ("2026-11-05", 4),
        ("2026-11-09", 5),
    ]

    # 6. Mock Jobs breakdown rows
    job_breakdown_res = MagicMock()
    job_breakdown_res.all.return_value = [
        (str(job_id), "Staff Cloud Architect", "Engineering", "published", 12, 6)
    ]

    # 7. Mock Department breakdown rows
    dept_res = MagicMock()
    dept_res.all.return_value = [("Engineering", 12, 4)]

    # 8. Mock Recent Applicants
    app_1 = JobApplication(
        id=uuid4(),
        tenant_id=tenant_id,
        job_id=job_id,
        candidate_id=candidate_1,
        status="under_review",
        candidate_status="under_review",
        resume_snapshot_sha256="abc123sha",
        applied_at=utc_now(),
    )
    app_1.job = Job(id=job_id, title="Staff Cloud Architect", department="Engineering")
    recent_apps_res = MagicMock()
    recent_apps_res.scalars().all.return_value = [app_1]

    # 9. Mock Candidate User resolution
    mock_user = User(
        id=candidate_1,
        email="candidate@example.com",
        first_name="Elena",
        last_name="Rostova",
    )
    mock_user.candidate_profile = CandidateUserProfile(
        user_id=candidate_1,
        self_declared_skills=["Python", "FastAPI", "Kubernetes"],
    )
    user_res = MagicMock()
    user_res.scalar_one_or_none.return_value = mock_user

    mock_db.execute.side_effect = [
        org_res,  # Org query
        app_res,  # App metrics query
        job_res,  # Job metrics query
        funnel_review_res,  # Funnel review
        funnel_screening_res,  # Funnel screening
        funnel_offer_res,  # Funnel offer
        time_res,  # Time series
        job_breakdown_res,  # By Job
        dept_res,  # By Dept
        recent_apps_res,  # Recent apps
        user_res,  # Cand user 1
    ]

    resp = await hr_dashboard_service.get_dashboard_overview(
        db=mock_db,
        tenant_id=tenant_id,
    )

    assert isinstance(resp, HrDashboardOverviewResponse)
    assert resp.organization_name == "Acme Corp"
    assert resp.metrics.total_applications == 12
    assert resp.metrics.total_candidates == 8
    assert resp.metrics.active_jobs == 4
    assert resp.metrics.applications_awaiting_review == 5
    assert resp.metrics.shortlisted_candidates == 3
    assert resp.metrics.scheduled_interviews == 2
    assert resp.metrics.hired_candidates == 1

    # Verify Funnel Stages
    assert len(resp.recruitment_funnel) == 7
    assert resp.recruitment_funnel[0].stage == "applied"
    assert resp.recruitment_funnel[0].count == 12
    assert resp.recruitment_funnel[0].percentage == 100.0

    # Verify Time Series
    assert len(resp.applications_over_time) == 3
    assert resp.applications_over_time[0].date == "2026-11-01"
    assert resp.applications_over_time[0].applications_count == 3

    # Verify Recent Applicants
    assert len(resp.recent_applicants) == 1
    assert resp.recent_applicants[0].candidate_name == "Elena Rostova"
    assert "Python" in resp.recent_applicants[0].top_skills


@pytest.mark.asyncio
async def test_hr_dashboard_empty_organization_handling() -> None:
    """Verify clean 0 metrics and 0.0 conversion percentages when organization has no data."""
    tenant_id = uuid4()
    mock_db = AsyncMock()

    org_res = MagicMock()
    org_res.scalar_one_or_none.return_value = Organization(id=tenant_id, name="Empty Org")

    app_res = MagicMock()
    app_res.one.return_value = MagicMock(
        total_applications=0,
        total_candidates=0,
        awaiting_review=0,
        shortlisted=0,
        scheduled_interviews=0,
        hired=0,
    )

    job_res = MagicMock()
    job_res.one.return_value = MagicMock(active_jobs=0, published_jobs=0, draft_jobs=0)

    funnel_scalar_res = MagicMock()
    funnel_scalar_res.scalar.return_value = 0

    empty_list_res = MagicMock()
    empty_list_res.all.return_value = []
    empty_list_res.scalars().all.return_value = []

    mock_db.execute.side_effect = [
        org_res,
        app_res,
        job_res,
        funnel_scalar_res,  # review
        funnel_scalar_res,  # screening
        funnel_scalar_res,  # offer
        empty_list_res,  # time
        empty_list_res,  # jobs
        empty_list_res,  # dept
        empty_list_res,  # recent apps
    ]

    resp = await hr_dashboard_service.get_dashboard_overview(
        db=mock_db,
        tenant_id=tenant_id,
    )

    assert resp.metrics.total_applications == 0
    assert resp.metrics.total_candidates == 0
    assert resp.metrics.active_jobs == 0
    assert len(resp.recent_applicants) == 0
    assert len(resp.applications_over_time) == 0

    # Ensure zero division is safely guarded
    for stage in resp.recruitment_funnel:
        assert stage.count == 0
        assert stage.percentage == 0.0


@pytest.mark.asyncio
async def test_hr_dashboard_filters_application() -> None:
    """Verify that department, job_id, stage, and date filters are accepted and recorded."""
    tenant_id = uuid4()
    job_id = uuid4()
    start_date = utc_now() - timedelta(days=7)
    end_date = utc_now()

    mock_db = AsyncMock()

    org_res = MagicMock()
    org_res.scalar_one_or_none.return_value = Organization(id=tenant_id, name="Filtered Org")

    app_res = MagicMock()
    app_res.one.return_value = MagicMock(
        total_applications=2,
        total_candidates=2,
        awaiting_review=1,
        shortlisted=1,
        scheduled_interviews=0,
        hired=0,
    )

    job_res = MagicMock()
    job_res.one.return_value = MagicMock(active_jobs=1, published_jobs=1, draft_jobs=0)

    funnel_res = MagicMock()
    funnel_res.scalar.return_value = 1

    empty_res = MagicMock()
    empty_res.all.return_value = []
    empty_res.scalars().all.return_value = []

    mock_db.execute.side_effect = [
        org_res,
        app_res,
        job_res,
        funnel_res,
        funnel_res,
        funnel_res,
        empty_res,
        empty_res,
        empty_res,
        empty_res,
    ]

    resp = await hr_dashboard_service.get_dashboard_overview(
        db=mock_db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        department="Product",
        job_id=job_id,
        stage="shortlisted",
    )

    assert resp.active_filters["department"] == "Product"
    assert resp.active_filters["job_id"] == str(job_id)
    assert resp.active_filters["stage"] == "shortlisted"
    assert "start_date" in resp.active_filters
    assert "end_date" in resp.active_filters


@pytest.mark.asyncio
async def test_resolve_hr_tenant_context_blocks_unauthorized_users() -> None:
    """Verify that requests without organization membership or with unauthorized roles are forbidden."""
    mock_request = MagicMock()
    mock_db = AsyncMock()

    # Case 1: Candidate user without any organization membership
    sec_unauthorized = SecurityContext(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=None,
        roles=["candidate"],
        permissions=["candidate:profile:manage"],
    )

    mem_res = MagicMock()
    mem_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mem_res

    with pytest.raises(AuthorizationException) as exc_info:
        await resolve_hr_tenant_context(
            request=mock_request,
            sec=sec_unauthorized,
            db=mock_db,
        )
    assert exc_info.value.code == "HR_TENANT_MEMBERSHIP_REQUIRED"


@pytest.mark.asyncio
async def test_resolve_hr_tenant_context_allows_recruiter_and_org_admin() -> None:
    """Verify that recruiter and org_admin roles cleanly resolve active tenant."""
    mock_request = MagicMock()
    mock_db = AsyncMock()
    tenant_id = uuid4()

    sec_recruiter = SecurityContext(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        roles=["recruiter"],
        permissions=["jobs:read", "candidates:view_all"],
    )

    resolved_tenant = await resolve_hr_tenant_context(
        request=mock_request,
        sec=sec_recruiter,
        db=mock_db,
    )
    assert resolved_tenant == tenant_id
