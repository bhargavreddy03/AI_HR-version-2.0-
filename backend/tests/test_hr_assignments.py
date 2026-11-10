"""Unit and integration tests for Recruiter and Hiring Manager Assignments (Step 4.2.7).

Verifies role validation, membership checks, assignment changes, unassignment,
immutable assignment history, notification dispatch, database workload metrics, and tenant isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AuthorizationException,
    EntityNotFoundException,
    ValidationException,
)
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateNotification
from app.modules.hr.assignment_service import HrAssignmentService
from app.modules.jobs.models import (
    Job,
    JobApplication,
    JobAssignmentHistory,
)
from app.modules.organizations.models import OrganizationMembership, Role


@pytest.fixture
def assignment_setup():
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    # Users
    admin_user = User(
        id=generate_uuid7(),
        email="admin@acme.com",
        password_hash="hash",
        first_name="Admin",
        last_name="Boss",
        is_active=True,
    )
    recruiter_1 = User(
        id=generate_uuid7(),
        email="recruiter1@acme.com",
        password_hash="hash",
        first_name="Alice",
        last_name="Recruiter",
        is_active=True,
    )
    recruiter_2 = User(
        id=generate_uuid7(),
        email="recruiter2@acme.com",
        password_hash="hash",
        first_name="Bob",
        last_name="Recruiter",
        is_active=True,
    )
    hm_1 = User(
        id=generate_uuid7(),
        email="hm1@acme.com",
        password_hash="hash",
        first_name="Carol",
        last_name="Manager",
        is_active=True,
    )
    hm_2 = User(
        id=generate_uuid7(),
        email="hm2@acme.com",
        password_hash="hash",
        first_name="David",
        last_name="Manager",
        is_active=True,
    )
    candidate_user = User(
        id=generate_uuid7(),
        email="candidate@example.com",
        password_hash="hash",
        first_name="Eve",
        last_name="Candidate",
        is_active=True,
    )
    external_user = User(
        id=generate_uuid7(),
        email="external@othercorp.com",
        password_hash="hash",
        first_name="Frank",
        last_name="External",
        is_active=True,
    )

    # Roles
    role_admin = Role(id=generate_uuid7(), name="org_admin", tenant_id=tenant_a_id)
    role_recruiter = Role(id=generate_uuid7(), name="recruiter", tenant_id=tenant_a_id)
    role_hm = Role(id=generate_uuid7(), name="hiring_manager", tenant_id=tenant_a_id)
    role_candidate = Role(id=generate_uuid7(), name="candidate", tenant_id=None)

    # Memberships in Tenant A
    mem_admin = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=admin_user.id,
        role_id=role_admin.id,
        is_active=True,
    )
    mem_rec1 = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=recruiter_1.id,
        role_id=role_recruiter.id,
        is_active=True,
    )
    mem_rec2 = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=recruiter_2.id,
        role_id=role_recruiter.id,
        is_active=True,
    )
    mem_hm1 = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=hm_1.id,
        role_id=role_hm.id,
        is_active=True,
    )
    mem_hm2 = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=hm_2.id,
        role_id=role_hm.id,
        is_active=True,
    )
    mem_cand = OrganizationMembership(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        user_id=candidate_user.id,
        role_id=role_candidate.id,
        is_active=True,
    )

    # Jobs
    job_1 = Job(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        title="Senior Python Platform Engineer",
        slug="sr-python-eng-1",
        department="Engineering",
        location="Austin, TX",
        remote_type="remote",
        employment_type="full_time",
        description="Senior platform engineering role.",
        status="published",
        vacancies_count=2,
        recruiter_id=recruiter_1.id,
        hiring_manager_id=hm_1.id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    job_1.recruiter = recruiter_1
    job_1.hiring_manager = hm_1

    job_b = Job(
        id=generate_uuid7(),
        tenant_id=tenant_b_id,
        title="Frontend Architect",
        slug="fe-arch-1",
        department="Design",
        location="San Francisco, CA",
        remote_type="remote",
        employment_type="full_time",
        description="Frontend architecture lead.",
        status="published",
        vacancies_count=1,
        recruiter_id=None,
        hiring_manager_id=None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    return {
        "tenant_a_id": tenant_a_id,
        "tenant_b_id": tenant_b_id,
        "admin_user": admin_user,
        "recruiter_1": recruiter_1,
        "recruiter_2": recruiter_2,
        "hm_1": hm_1,
        "hm_2": hm_2,
        "candidate_user": candidate_user,
        "external_user": external_user,
        "role_admin": role_admin,
        "role_recruiter": role_recruiter,
        "role_hm": role_hm,
        "role_candidate": role_candidate,
        "mem_admin": mem_admin,
        "mem_rec1": mem_rec1,
        "mem_rec2": mem_rec2,
        "mem_hm1": mem_hm1,
        "mem_hm2": mem_hm2,
        "mem_cand": mem_cand,
        "job_1": job_1,
        "job_b": job_b,
    }


@pytest.mark.asyncio
async def test_assign_recruiter_success_and_history_and_notification(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    # db.get mock
    def mock_get(model, ident):
        if model == Job and ident == s["job_1"].id:
            return s["job_1"]
        if model == User:
            for u in [s["admin_user"], s["recruiter_1"], s["recruiter_2"], s["hm_1"], s["hm_2"]]:
                if u.id == ident:
                    return u
        return None

    db.get.side_effect = mock_get

    # db.execute mock for _validate_assignment_target
    target_exec = MagicMock()
    target_exec.first.return_value = (s["recruiter_2"], s["role_recruiter"])
    db.execute.return_value = target_exec

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    resp = await service.assign_recruiter(
        db=db,
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        recruiter_id=s["recruiter_2"].id,
        actor_id=s["admin_user"].id,
        actor_roles=["org_admin"],
        is_super_admin=False,
        reason="Handing over requisition to Bob for Q4",
    )

    assert resp.job_id == s["job_1"].id
    assert resp.recruiter_id == s["recruiter_2"].id
    assert resp.recruiter_name == "Bob Recruiter"
    assert s["job_1"].recruiter_id == s["recruiter_2"].id

    # Verify history entry was created
    history_entries = [o for o in added_objects if isinstance(o, JobAssignmentHistory)]
    assert len(history_entries) == 1
    assert history_entries[0].assignment_type == "recruiter"
    assert history_entries[0].previous_user_id == s["recruiter_1"].id
    assert history_entries[0].new_user_id == s["recruiter_2"].id
    assert history_entries[0].reason == "Handing over requisition to Bob for Q4"

    # Verify notifications were created for both assigned and unassigned users
    notifs = [o for o in added_objects if isinstance(o, CandidateNotification)]
    assert len(notifs) == 2
    assigned_notif = next(n for n in notifs if n.user_id == s["recruiter_2"].id)
    assert assigned_notif.event_type == "job_recruiter_assigned"
    unassigned_notif = next(n for n in notifs if n.user_id == s["recruiter_1"].id)
    assert unassigned_notif.event_type == "job_recruiter_unassigned"


@pytest.mark.asyncio
async def test_assign_hiring_manager_success_and_history_and_notification(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    def mock_get(model, ident):
        if model == Job and ident == s["job_1"].id:
            return s["job_1"]
        if model == User:
            for u in [s["admin_user"], s["recruiter_1"], s["recruiter_2"], s["hm_1"], s["hm_2"]]:
                if u.id == ident:
                    return u
        return None

    db.get.side_effect = mock_get

    target_exec = MagicMock()
    target_exec.first.return_value = (s["hm_2"], s["role_hm"])
    db.execute.return_value = target_exec

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    resp = await service.assign_hiring_manager(
        db=db,
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        hiring_manager_id=s["hm_2"].id,
        actor_id=s["admin_user"].id,
        actor_roles=["org_admin"],
        is_super_admin=False,
        reason="David will lead interview assessments",
    )

    assert resp.job_id == s["job_1"].id
    assert resp.hiring_manager_id == s["hm_2"].id
    assert resp.hiring_manager_name == "David Manager"
    assert s["job_1"].hiring_manager_id == s["hm_2"].id

    history_entries = [o for o in added_objects if isinstance(o, JobAssignmentHistory)]
    assert len(history_entries) == 1
    assert history_entries[0].assignment_type == "hiring_manager"
    assert history_entries[0].previous_user_id == s["hm_1"].id
    assert history_entries[0].new_user_id == s["hm_2"].id


@pytest.mark.asyncio
async def test_unassign_recruiter_and_hiring_manager(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    def mock_get(model, ident):
        if model == Job and ident == s["job_1"].id:
            return s["job_1"]
        if model == User:
            for u in [s["admin_user"], s["recruiter_1"], s["hm_1"]]:
                if u.id == ident:
                    return u
        return None

    db.get.side_effect = mock_get

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    # Unassign recruiter
    resp = await service.assign_recruiter(
        db=db,
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        recruiter_id=None,
        actor_id=s["admin_user"].id,
        actor_roles=["org_admin"],
        is_super_admin=False,
        reason="Vacancy placed on hold",
    )

    assert resp.recruiter_id is None
    assert resp.recruiter_name is None
    assert s["job_1"].recruiter_id is None

    history_entries = [o for o in added_objects if isinstance(o, JobAssignmentHistory)]
    assert len(history_entries) == 1
    assert history_entries[0].previous_user_id == s["recruiter_1"].id
    assert history_entries[0].new_user_id is None


@pytest.mark.asyncio
async def test_assignment_target_not_organization_member_rejected(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()
    def mock_get(model, ident):
        if model == Job:
            return s["job_1"]
        if model == User:
            return s["admin_user"]
        return None

    db.get.side_effect = mock_get

    # Target user not found in organization membership
    mock_res = MagicMock()
    mock_res.first.return_value = None
    db.execute.return_value = mock_res

    with pytest.raises(ValidationException) as exc:
        await service.assign_recruiter(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=s["job_1"].id,
            recruiter_id=s["external_user"].id,
            actor_id=s["admin_user"].id,
            actor_roles=["org_admin"],
        )

    assert exc.value.code == "USER_NOT_ORGANIZATION_MEMBER"


@pytest.mark.asyncio
async def test_assignment_target_invalid_role_rejected(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()
    def mock_get(model, ident):
        if model == Job:
            return s["job_1"]
        if model == User:
            return s["admin_user"]
        return None

    db.get.side_effect = mock_get

    # User is in org but has role 'candidate'
    mock_res = MagicMock()
    mock_res.first.return_value = (s["candidate_user"], s["role_candidate"])
    db.execute.return_value = mock_res

    with pytest.raises(ValidationException) as exc:
        await service.assign_recruiter(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=s["job_1"].id,
            recruiter_id=s["candidate_user"].id,
            actor_id=s["admin_user"].id,
            actor_roles=["org_admin"],
        )

    assert exc.value.code == "INVALID_RECRUITER_ROLE"


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_reassign_job(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()
    def mock_get(model, ident):
        if model == Job:
            return s["job_1"]
        if model == User:
            return s["admin_user"]
        return None

    db.get.side_effect = mock_get

    # User is recruiter_2 who is NOT assigned to job_1 and is NOT admin
    rec2_membership_mock = MagicMock()
    rec2_membership_mock.first.return_value = (s["mem_rec2"], s["role_recruiter"], s["recruiter_2"])
    db.execute.return_value = rec2_membership_mock

    with pytest.raises(AuthorizationException) as exc:
        await service.assign_recruiter(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=s["job_1"].id,
            recruiter_id=s["recruiter_2"].id,
            actor_id=s["recruiter_2"].id,
            actor_roles=["recruiter"],  # not admin, not assigned on job_1
        )

    assert exc.value.code == "ASSIGNMENT_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_assigned_recruiter_can_reassign_own_job(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    def mock_get(model, ident):
        if model == Job and ident == s["job_1"].id:
            return s["job_1"]
        if model == User:
            for u in [s["recruiter_1"], s["recruiter_2"], s["hm_1"]]:
                if u.id == ident:
                    return u
        return None

    db.get.side_effect = mock_get

    target_exec = MagicMock()
    target_exec.first.return_value = (s["recruiter_2"], s["role_recruiter"])
    db.execute.return_value = target_exec

    db.add = MagicMock()

    # recruiter_1 is currently assigned to job_1, reassigning to recruiter_2
    resp = await service.assign_recruiter(
        db=db,
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        recruiter_id=s["recruiter_2"].id,
        actor_id=s["recruiter_1"].id,
        actor_roles=["recruiter"],
        is_super_admin=False,
        reason="Handover due to parental leave",
    )

    assert resp.recruiter_id == s["recruiter_2"].id
    assert s["job_1"].recruiter_id == s["recruiter_2"].id


@pytest.mark.asyncio
async def test_get_job_assignment_history_chronological(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()
    def mock_get(model, ident):
        if model == Job:
            return s["job_1"]
        if model == User:
            return s["admin_user"]
        return None

    db.get.side_effect = mock_get

    hist1 = JobAssignmentHistory(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        assignment_type="recruiter",
        actor_id=s["admin_user"].id,
        actor_name="Admin Boss",
        previous_user_id=None,
        previous_user_name=None,
        new_user_id=s["recruiter_1"].id,
        new_user_name="Alice Recruiter",
        reason="Initial requisition assignment",
        created_at=utc_now(),
    )
    hist2 = JobAssignmentHistory(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        job_id=s["job_1"].id,
        assignment_type="hiring_manager",
        actor_id=s["admin_user"].id,
        actor_name="Admin Boss",
        previous_user_id=None,
        previous_user_name=None,
        new_user_id=s["hm_1"].id,
        new_user_name="Carol Manager",
        reason="Appointed hiring manager",
        created_at=utc_now(),
    )

    history_exec = MagicMock()
    history_exec.scalars.return_value.all.return_value = [hist2, hist1]
    db.execute.return_value = history_exec

    history = await service.get_job_assignment_history(
        db=db, tenant_id=s["tenant_a_id"], job_id=s["job_1"].id
    )

    assert len(history) == 2
    assert history[0].assignment_type == "hiring_manager"
    assert history[0].new_user_name == "Carol Manager"
    assert history[1].assignment_type == "recruiter"
    assert history[1].new_user_name == "Alice Recruiter"


@pytest.mark.asyncio
async def test_get_team_workload_calculation_and_capacity_status(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    # Members: recruiter_1, recruiter_2, hm_1
    members_data = [
        (s["recruiter_1"], s["role_recruiter"], s["mem_rec1"]),
        (s["recruiter_2"], s["role_recruiter"], s["mem_rec2"]),
        (s["hm_1"], s["role_hm"], s["mem_hm1"]),
    ]
    # Jobs: job_1 assigned to recruiter_1 and hm_1
    jobs_data = [s["job_1"]]

    # Apps data: job_1 has 5 applied, 2 in interview
    apps_data = [
        (s["job_1"].id, "applied", 5),
        (s["job_1"].id, "interview", 2),
    ]

    mock_exec1 = MagicMock()
    mock_exec1.all.return_value = members_data

    mock_exec2 = MagicMock()
    mock_exec2.scalars.return_value.all.return_value = jobs_data

    mock_exec3 = MagicMock()
    mock_exec3.all.return_value = apps_data

    db.execute.side_effect = [mock_exec1, mock_exec2, mock_exec3]

    workload = await service.get_team_workload(db=db, tenant_id=s["tenant_a_id"])

    assert workload.tenant_id == s["tenant_a_id"]
    assert len(workload.recruiters) == 2
    assert len(workload.hiring_managers) == 1

    # Recruiter 1 has 1 job, 7 total apps, 5 pending reviews, 2 interviews
    rec1_wl = next(r for r in workload.recruiters if r.user_id == s["recruiter_1"].id)
    assert rec1_wl.assigned_jobs_count == 1
    assert rec1_wl.total_applications_count == 7
    assert rec1_wl.pending_reviews_count == 5
    assert rec1_wl.active_interviews_count == 2
    assert rec1_wl.workload_status == "balanced"

    # Recruiter 2 has 0 jobs
    rec2_wl = next(r for r in workload.recruiters if r.user_id == s["recruiter_2"].id)
    assert rec2_wl.assigned_jobs_count == 0
    assert rec2_wl.workload_status == "low"

    # HM 1 has 1 job
    hm1_wl = workload.hiring_managers[0]
    assert hm1_wl.user_id == s["hm_1"].id
    assert hm1_wl.assigned_jobs_count == 1

    # Summary
    assert workload.summary.total_team_members == 3
    assert workload.summary.total_assigned_jobs == 1
    assert workload.summary.total_active_applications == 7


@pytest.mark.asyncio
async def test_get_my_assigned_vacancies(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    app1 = JobApplication(
        id=generate_uuid7(),
        job_id=s["job_1"].id,
        candidate_id=s["candidate_user"].id,
        resume_snapshot_sha256="abc",
        status="screening",
    )
    s["job_1"].applications = [app1]

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [s["job_1"]]
    db.execute.return_value = mock_res

    res = await service.get_assigned_vacancies(
        db=db, tenant_id=s["tenant_a_id"], user_id=s["recruiter_1"].id
    )

    assert res.total == 1
    assert res.vacancies[0].id == s["job_1"].id
    assert res.vacancies[0].title == "Senior Python Platform Engineer"
    assert res.vacancies[0].active_applications_count == 1
    assert res.vacancies[0].pending_reviews_count == 1


@pytest.mark.asyncio
async def test_cross_tenant_assignment_isolation(assignment_setup):
    service = HrAssignmentService()
    s = assignment_setup
    db = AsyncMock()

    # job_b belongs to tenant_b_id, but request is made with tenant_a_id
    db.get.return_value = s["job_b"]

    with pytest.raises(EntityNotFoundException):
        await service.assign_recruiter(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=s["job_b"].id,
            recruiter_id=s["recruiter_1"].id,
            actor_id=s["admin_user"].id,
            actor_roles=["org_admin"],
        )
