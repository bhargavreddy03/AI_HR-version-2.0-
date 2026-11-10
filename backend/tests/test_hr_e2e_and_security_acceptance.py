"""Step 4.2.9 — HR / Recruiter Portal Complete End-to-End, Tenant-Isolation and Security Acceptance Suite.

Validates:
1. Complete 15-step end-to-end recruiter workflow (Auth -> Dashboard -> Create -> Edit -> Approve ->
   Publish -> Candidate Apply -> View Application -> Candidate Profile -> Secure Resume -> Review ->
   Pipeline Move -> Assignment -> Internal Note -> Activity History).
2. Multi-tenant isolation between Organization Alpha and Organization Beta across jobs, applications,
   internal notes, candidate profiles, and role visibility boundaries.
3. Security posture verification: IDOR prevention, RBAC enforcement, separation of duties, unauthorized
   publication blocking, SQL injection / XSS input handling, candidate privacy isolation barrier.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
    ValidationException,
)
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.candidates.models import (
    CandidateResume,
)
from app.modules.documents.storage import StorageService
from app.modules.hr.applicant_service import HrApplicantService
from app.modules.hr.assignment_service import HrAssignmentService
from app.modules.hr.lifecycle_schemas import JobLifecycleActionRequest
from app.modules.hr.lifecycle_service import HrJobLifecycleService
from app.modules.hr.pipeline_service import HrPipelineService
from app.modules.hr.requisition_schemas import (
    JobRequisitionCreate,
    JobRequisitionRead,
    JobRequisitionUpdate,
)
from app.modules.hr.review_schemas import (
    CreateInternalNoteRequest,
    CreateRecruitmentTaskRequest,
    SubmitReviewFeedbackRequest,
)
from app.modules.hr.review_service import HrReviewService
from app.modules.hr.service import hr_dashboard_service, hr_requisition_service
from app.modules.jobs.models import (
    ApplicationStageHistory,
    CandidateInternalNote,
    CandidateReviewFeedback,
    Job,
    JobApplication,
)
from app.modules.organizations.models import Organization


@pytest.fixture(autouse=True)
def mock_celery_notifications():
    """Mock Celery delay dispatches so tests execute completely offline."""
    with patch("app.modules.notifications.tasks.dispatch_job_lifecycle_notification.delay") as m1, \
         patch("app.modules.notifications.tasks.dispatch_candidate_email_notification.delay") as m2:
        yield {"lifecycle": m1, "candidate": m2}


@pytest.fixture
def acceptance_fixture():
    # Organization A (Alpha Corp)
    tenant_a_id = uuid4()
    org_a = Organization(id=tenant_a_id, name="Alpha Corp", slug="alpha-corp", status="active")

    # Organization B (Beta Corp)
    tenant_b_id = uuid4()
    org_b = Organization(id=tenant_b_id, name="Beta Corp", slug="beta-corp", status="active")

    # Org A Users
    recruiter_a = User(
        id=generate_uuid7(),
        email="alice.recruiter@alpha.com",
        first_name="Alice",
        last_name="Recruiter",
        password_hash="hash",
        is_active=True,
    )
    hm_a = User(
        id=generate_uuid7(),
        email="bob.hm@alpha.com",
        first_name="Bob",
        last_name="Manager",
        password_hash="hash",
        is_active=True,
    )
    admin_a = User(
        id=generate_uuid7(),
        email="carol.admin@alpha.com",
        first_name="Carol",
        last_name="Admin",
        password_hash="hash",
        is_active=True,
    )

    # Org B Users
    recruiter_b = User(
        id=generate_uuid7(),
        email="dan.recruiter@beta.com",
        first_name="Dan",
        last_name="Recruiter",
        password_hash="hash",
        is_active=True,
    )

    # Candidate 1 (Applies to Org A)
    cand_user_1 = User(
        id=generate_uuid7(),
        email="jane.candidate@example.com",
        first_name="Jane",
        last_name="Candidate",
        password_hash="hash",
        is_active=True,
    )
    cand_profile_1 = CandidateUserProfile(
        user_id=cand_user_1.id,
        phone="+1 555-0100",
        headline="Principal Cloud Infrastructure Architect",
        bio="Deep distributed systems, Kubernetes and cloud architecture expertise.",
        location_city="Seattle",
        location_country="United States",
        work_authorization="US Citizen",
        self_declared_skills=["Python", "Go", "Kubernetes", "AWS", "FastAPI"],
    )

    # Candidate 2 (Never applied to Org A)
    cand_user_2 = User(
        id=generate_uuid7(),
        email="john.stranger@example.com",
        first_name="John",
        last_name="Stranger",
        password_hash="hash",
        is_active=True,
    )
    cand_profile_2 = CandidateUserProfile(
        user_id=cand_user_2.id,
        headline="Data Analyst",
    )

    # Candidate 1 Resume
    cand_resume = CandidateResume(
        id=generate_uuid7(),
        user_id=cand_user_1.id,
        storage_key="resumes/cand1_jane_doe.pdf",
        filename="jane_doe_cv.pdf",
        mime_type="application/pdf",
        file_size_bytes=1048576,
        content_sha256="aabbcc112233445566778899",
        is_default=True,
    )

    return {
        "tenant_a_id": tenant_a_id,
        "org_a": org_a,
        "tenant_b_id": tenant_b_id,
        "org_b": org_b,
        "recruiter_a": recruiter_a,
        "hm_a": hm_a,
        "admin_a": admin_a,
        "recruiter_b": recruiter_b,
        "cand_user_1": cand_user_1,
        "cand_profile_1": cand_profile_1,
        "cand_user_2": cand_user_2,
        "cand_profile_2": cand_profile_2,
        "cand_resume": cand_resume,
    }


# ==============================================================================
# SECTION 1: END-TO-END RECRUITER JOURNEY (15 MANDATORY STEPS)
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_recruiter_journey_15_steps(acceptance_fixture):
    """Executes the complete 15-step end-to-end recruitment lifecycle."""
    s = acceptance_fixture
    tenant_id = s["tenant_a_id"]
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    # Step 1: HR user logs in / security context established
    recruiter = s["recruiter_a"]
    assert recruiter.is_active is True
    assert recruiter.email == "alice.recruiter@alpha.com"

    # Step 2: HR opens dashboard and loads organization-scoped overview
    dash_service = hr_dashboard_service
    # Mock dashboard queries
    mock_org_res = MagicMock()
    mock_org_res.scalar_one_or_none.return_value = s["org_a"]

    app_metrics_mock = MagicMock(
        total_applications=1,
        total_candidates=1,
        awaiting_review=1,
        shortlisted=0,
        scheduled_interviews=0,
        hired=0,
    )
    mock_app_res = MagicMock()
    mock_app_res.one.return_value = app_metrics_mock

    job_metrics_mock = MagicMock(
        active_jobs=1,
        published_jobs=1,
        draft_jobs=0,
    )
    mock_job_res = MagicMock()
    mock_job_res.one.return_value = job_metrics_mock

    funnel_rev = MagicMock(scalar=MagicMock(return_value=1))
    funnel_scr = MagicMock(scalar=MagicMock(return_value=0))
    funnel_off = MagicMock(scalar=MagicMock(return_value=0))
    time_res = MagicMock(all=MagicMock(return_value=[]))
    job_breakdown_res = MagicMock(all=MagicMock(return_value=[]))
    dept_res = MagicMock(all=MagicMock(return_value=[]))
    recent_apps_res = MagicMock()
    recent_apps_res.scalars().all.return_value = []

    db.execute = AsyncMock(side_effect=[
        mock_org_res,       # Org check
        mock_app_res,       # App metrics query
        mock_job_res,       # Job metrics query
        funnel_rev,         # Funnel review
        funnel_scr,         # Funnel screening
        funnel_off,         # Funnel offer
        time_res,           # Time series
        job_breakdown_res,  # By Job
        dept_res,           # By Dept
        recent_apps_res,    # Recent apps
    ])
    dash_overview = await dash_service.get_dashboard_overview(db, tenant_id)
    assert str(dash_overview.tenant_id) == str(tenant_id)
    assert dash_overview.organization_name == "Alpha Corp"

    # Step 3: HR creates a job requisition
    job_service = hr_requisition_service
    job_entity = Job(
        id=generate_uuid7(),
        tenant_id=tenant_id,
        title="Lead Distributed Systems Engineer",
        slug="lead-distributed-systems-engineer-12345678",
        department="Platform Infrastructure",
        location="Seattle, WA",
        remote_type="hybrid",
        employment_type="full_time",
        experience_level="lead",
        description="Build high-throughput distributed microservices.",
        skills_required=["Python", "Go", "Kubernetes", "PostgreSQL"],
        vacancies_count=2,
        salary_currency="USD",
        salary_min=150000,
        salary_max=220000,
        status="draft",
        approval_status="draft",
        visibility="public",
        recruiter_id=recruiter.id,
        hiring_manager_id=s["hm_a"].id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    job_entity.recruiter = recruiter
    job_entity.hiring_manager = s["hm_a"]

    create_input = JobRequisitionCreate(
        title="Lead Distributed Systems Engineer",
        department="Platform Infrastructure",
        location="Seattle, WA",
        remote_type="hybrid",
        employment_type="full_time",
        experience_level="lead",
        description="Build high-throughput distributed microservices.",
        skills_required=["Python", "Go", "Kubernetes", "PostgreSQL"],
        vacancies_count=2,
        recruiter_id=recruiter.id,
        hiring_manager_id=s["hm_a"].id,
    )
    job_res = MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity))
    count_res = MagicMock(scalar_one=MagicMock(return_value=0))
    db.execute = AsyncMock(side_effect=[job_res, count_res])

    job_read = await job_service.create_requisition(db, tenant_id, create_input)
    assert job_read.title == "Lead Distributed Systems Engineer"
    assert job_read.status == "draft"
    assert job_read.tenant_id == tenant_id

    # Step 4: HR saves and edits job details
    update_input = JobRequisitionUpdate(
        title="Principal Distributed Systems Architect",
        description="Lead architecture and high-throughput microservices.",
    )
    job_entity.title = "Principal Distributed Systems Architect"
    db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity)),
        MagicMock(scalar_one=MagicMock(return_value=0)),
    ])
    updated_job = await job_service.update_requisition(db, tenant_id, job_entity.id, update_input)
    assert updated_job.title == "Principal Distributed Systems Architect"

    # Step 5: Recruiter submits draft for approval, Hiring Manager approves
    lifecycle_service = HrJobLifecycleService()

    def mock_get_req_fn(db_conn, t_id, j_id):
        return JobRequisitionRead(
            id=job_entity.id,
            tenant_id=job_entity.tenant_id,
            title=job_entity.title,
            slug=job_entity.slug,
            department=job_entity.department,
            location=job_entity.location,
            remote_type=job_entity.remote_type,
            employment_type=job_entity.employment_type,
            experience_level=job_entity.experience_level,
            description=job_entity.description,
            status=job_entity.status,
            approval_status=job_entity.approval_status,
            visibility=job_entity.visibility,
            salary_currency="USD",
            created_at=job_entity.created_at,
            updated_at=job_entity.updated_at,
        )

    with patch("app.modules.hr.service.hr_requisition_service.get_requisition", AsyncMock(side_effect=mock_get_req_fn)):
        # 5a. Submit for approval
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=recruiter)),
        ])
        res_submit = await lifecycle_service.execute_transition(
            db=db,
            tenant_id=tenant_id,
            job_id=job_entity.id,
            user_id=recruiter.id,
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="submit_for_approval"),
        )
        assert res_submit.job.status == "pending_approval"
        job_entity.status = "pending_approval"

        # 5b. Hiring manager approves (Separation of duties respected)
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=s["hm_a"])),
        ])
        res_approved = await lifecycle_service.execute_transition(
            db=db,
            tenant_id=tenant_id,
            job_id=job_entity.id,
            user_id=s["hm_a"].id,
            user_roles=["hiring_manager"],
            request=JobLifecycleActionRequest(action="approve"),
        )
        assert res_approved.job.status == "approved"
        job_entity.status = "approved"

        # Step 6: Job is published
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=job_entity)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=s["admin_a"])),
        ])
        res_pub = await lifecycle_service.execute_transition(
            db=db,
            tenant_id=tenant_id,
            job_id=job_entity.id,
            user_id=s["admin_a"].id,
            user_roles=["admin"],
            request=JobLifecycleActionRequest(action="publish"),
        )
        assert res_pub.job.status == "published"
        job_entity.status = "published"
        assert job_entity.published_at is not None

    # Step 7: Candidate applies through Step 4.1
    cand_app = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_id,
        job_id=job_entity.id,
        candidate_id=s["cand_user_1"].id,
        status="applied",
        candidate_status="submitted",
        applied_at=utc_now(),
        resume_id=s["cand_resume"].id,
        resume_snapshot_sha256=s["cand_resume"].content_sha256,
        cover_letter="Excited to lead distributed systems at Alpha Corp.",
        timeline=[{"status": "applied", "changed_at": utc_now().isoformat(), "is_internal": False}],
    )
    cand_app.job = job_entity
    cand_app.candidate = s["cand_user_1"]
    cand_app.resume = s["cand_resume"]

    # Step 8: HR views the application in applicant list
    storage = StorageService()
    storage.generate_presigned_download_url = MagicMock(return_value="https://storage.cloud.com/signed/cand1.pdf?token=xyz")
    applicant_service = HrApplicantService(storage_service=storage)

    mock_count = MagicMock()
    mock_count.scalar.return_value = 1
    mock_apps_row = MagicMock(all=MagicMock(return_value=[
        (cand_app, job_entity, s["cand_user_1"], s["cand_profile_1"], s["cand_resume"])
    ]))
    list_exp_res = MagicMock()
    list_exp_res.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[mock_count, mock_apps_row, list_exp_res])
    applicant_list = await applicant_service.list_applicants(db, tenant_id)
    assert applicant_list.total == 1
    assert applicant_list.items[0].candidate_name == "Jane Candidate"
    assert applicant_list.items[0].job_title == "Principal Distributed Systems Architect"

    # Step 9: HR opens candidate profile
    auth_res = MagicMock()
    auth_res.scalar_one_or_none.return_value = cand_app.id
    user_res = MagicMock()
    user_res.scalar_one_or_none.return_value = s["cand_user_1"]
    prof_res = MagicMock()
    prof_res.scalar_one_or_none.return_value = s["cand_profile_1"]
    exp_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    edu_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    cert_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    proj_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    lang_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    org_hist_res = MagicMock()
    org_hist_res.all.return_value = [(cand_app, job_entity)]
    target_res = MagicMock()
    target_res.first.return_value = (cand_app, job_entity, s["cand_resume"])

    db.execute = AsyncMock(side_effect=[
        auth_res, user_res, prof_res, exp_res, edu_res, cert_res, proj_res, lang_res, org_hist_res, target_res
    ])
    cand_detail = await applicant_service.get_candidate_details(
        db, tenant_id, s["cand_user_1"].id, cand_app.id
    )
    assert cand_detail.full_name == "Jane Candidate"
    assert cand_detail.email == "jane.candidate@example.com"
    assert cand_detail.current_application is not None
    assert cand_detail.current_application.status == "applied"

    # Step 10: HR accesses submitted resume securely via presigned URL
    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = cand_app
    resume_res = MagicMock()
    resume_res.scalar_one_or_none.return_value = s["cand_resume"]
    db.execute = AsyncMock(side_effect=[app_res, resume_res])

    resume_access = await applicant_service.get_resume_signed_url(
        db=db,
        tenant_id=tenant_id,
        application_id=cand_app.id,
        actor_user_id=recruiter.id,
    )
    assert "token=xyz" in resume_access.download_url
    assert resume_access.filename == "jane_doe_cv.pdf"

    # Step 11: HR reviews application & submits collaborative review scorecard
    review_service = HrReviewService()
    db.get = AsyncMock(return_value=cand_app)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    scorecard_payload = SubmitReviewFeedbackRequest(
        recommendation="strong_yes",
        technical_rating=5,
        communication_rating=4,
        cultural_rating=5,
        overall_rating=5,
        summary="Exceptional systems design background. Recommended for immediate interview.",
        pros=["Expert Kubernetes architecture", "Clear communication"],
        cons=[],
    )
    scorecard = await review_service.submit_review_feedback(
        db=db,
        tenant_id=tenant_id,
        application_id=cand_app.id,
        reviewer_id=recruiter.id,
        reviewer_name="Alice Recruiter",
        reviewer_role="recruiter",
        request=scorecard_payload,
    )
    assert scorecard.recommendation == "strong_yes"
    assert scorecard.overall_rating == 5

    # Step 12: HR moves application through valid pipeline stage (applied -> screening)
    pipeline_service = HrPipelineService()
    cand_app.stage_history = []
    db.execute = AsyncMock(side_effect=[
        # Application check
        MagicMock(scalar_one_or_none=MagicMock(return_value=cand_app)),
        # Custom stage config
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ])
    res_move = await pipeline_service.transition_stage(
        db=db,
        tenant_id=tenant_id,
        application_id=cand_app.id,
        target_stage="screening",
        actor_id=recruiter.id,
        actor_role="recruiter",
        actor_name="Alice Recruiter",
        reason="Passed initial recruiter screening review",
    )
    assert res_move.new_stage == "screening"
    assert cand_app.status == "screening"

    # Step 13: HR updates job recruiter & hiring manager assignments
    assignment_service = HrAssignmentService()

    def mock_get_job(model, ident):
        if model == Job:
            return job_entity
        if model == JobApplication:
            return cand_app
        if model == User:
            if ident == recruiter.id:
                return recruiter
            if ident == s["hm_a"].id:
                return s["hm_a"]
            if ident == s["admin_a"].id:
                return s["admin_a"]
        return None

    db.get = AsyncMock(side_effect=mock_get_job)
    role_mock = MagicMock()
    role_mock.name = "recruiter"
    target_exec = MagicMock()
    target_exec.first.return_value = (recruiter, role_mock)
    db.execute = AsyncMock(return_value=target_exec)

    assign_res = await assignment_service.assign_recruiter(
        db=db,
        tenant_id=tenant_id,
        job_id=job_entity.id,
        recruiter_id=recruiter.id,
        actor_id=s["admin_a"].id,
        actor_roles=["admin"],
        reason="Assigned lead recruiter",
    )
    assert assign_res.recruiter_name == "Alice Recruiter"

    # Step 14: HR records confidential internal note
    db.execute = AsyncMock(side_effect=[
        # Candidate belongs to tenant check
        MagicMock(scalar_one_or_none=MagicMock(return_value=cand_app.id)),
    ])
    note_payload = CreateInternalNoteRequest(
        application_id=cand_app.id,
        content="Candidate requested compensation discussion at offer stage.",
        category="compensation",
        is_confidential=True,
    )
    note = await review_service.add_internal_note(
        db=db,
        tenant_id=tenant_id,
        candidate_id=s["cand_user_1"].id,
        author_id=recruiter.id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        request=note_payload,
    )
    assert note.is_confidential is True
    assert note.category == "compensation"

    # Step 15: HR views unified candidate activity timeline
    stage_hist_entry = ApplicationStageHistory(
        id=generate_uuid7(), tenant_id=tenant_id, application_id=cand_app.id,
        previous_stage="applied", new_stage="screening", actor_id=recruiter.id,
        actor_role="recruiter", reason="Passed screening", created_at=utc_now()
    )
    stage_hist_entry.actor = recruiter

    db.execute = AsyncMock(side_effect=[
        # 1. Candidate check
        MagicMock(scalar_one_or_none=MagicMock(return_value=cand_app.id)),
        # 2. Applications query
        MagicMock(all=MagicMock(return_value=[(cand_app, job_entity)])),
        # 3. Stage history query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[stage_hist_entry])))),
        # 4. Internal notes query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[
            CandidateInternalNote(
                id=note.id, tenant_id=tenant_id, candidate_id=s["cand_user_1"].id,
                author_id=recruiter.id, author_name="Alice Recruiter", author_role="recruiter",
                content=note.content, category=note.category, is_confidential=True, created_at=utc_now()
            )
        ])))),
        # 5. Reviews query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[
            CandidateReviewFeedback(
                id=scorecard.id, tenant_id=tenant_id, application_id=cand_app.id,
                reviewer_id=recruiter.id, reviewer_name="Alice Recruiter", reviewer_role="recruiter",
                recommendation="strong_yes", summary="Great fit", pros=[], cons=[], created_at=utc_now()
            )
        ])))),
        # 6. Tasks query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        # 7. Assignment history query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    timeline = await review_service.get_candidate_timeline(
        db, tenant_id, s["cand_user_1"].id, cand_app.id, is_internal_viewer=True
    )
    assert timeline.total_events >= 4
    event_types = {e.event_type for e in timeline.events}
    assert "application_submitted" in event_types
    assert "stage_transition" in event_types
    assert "note_added" in event_types
    assert "review_submitted" in event_types


# ==============================================================================
# SECTION 2: TENANT-ISOLATION TESTS (ORG A vs ORG B)
# ==============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_jobs_cross_tenant_blocked(acceptance_fixture):
    """Organization B cannot access or update Organization A's job requisitions."""
    s = acceptance_fixture
    db = AsyncMock()
    service = hr_requisition_service

    # Job belongs to Org A
    job_a = Job(id=generate_uuid7(), tenant_id=s["tenant_a_id"], title="Secret Job A", status="draft")

    # Org B queries Org A's job -> RLS / tenant filter returns None
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    res_get = await service.get_requisition(db, tenant_id=s["tenant_b_id"], job_id=job_a.id)
    assert res_get is None

    res_update = await service.update_requisition(
        db, tenant_id=s["tenant_b_id"], job_id=job_a.id,
        data=JobRequisitionUpdate(title="Hijacked Title")
    )
    assert res_update is None


@pytest.mark.asyncio
async def test_tenant_isolation_applications_cross_tenant_blocked(acceptance_fixture):
    """Organization B cannot access applications belonging to Organization A."""
    s = acceptance_fixture
    db = AsyncMock()
    applicant_service = HrApplicantService(storage_service=StorageService())

    # Application belongs to Org A
    app_a = JobApplication(id=generate_uuid7(), tenant_id=s["tenant_a_id"], status="applied")

    # Org B attempts to retrieve Org A's candidate detail
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises((AuthorizationException, EntityNotFoundException)):
        await applicant_service.get_candidate_details(
            db, tenant_id=s["tenant_b_id"], candidate_id=s["cand_user_1"].id, application_id=app_a.id
        )


@pytest.mark.asyncio
async def test_tenant_isolation_internal_notes_cross_tenant_blocked(acceptance_fixture):
    """Organization B cannot read or modify Organization A's internal notes."""
    s = acceptance_fixture
    db = AsyncMock()
    review_service = HrReviewService()

    note_a = CandidateInternalNote(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["cand_user_1"].id,
        content="Confidential salary data for Org A",
        author_id=s["recruiter_a"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        is_confidential=False,
    )

    # Org B recruiter attempts to delete Org A note
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises(EntityNotFoundException):
        await review_service.delete_internal_note(
            db, tenant_id=s["tenant_b_id"], note_id=note_a.id,
            actor_id=s["recruiter_b"].id, is_admin=False
        )


@pytest.mark.asyncio
async def test_tenant_isolation_unauthorized_candidate_profile_blocked(acceptance_fixture):
    """Recruiter cannot view candidate who has never applied to their organization."""
    s = acceptance_fixture
    db = AsyncMock()
    applicant_service = HrApplicantService(storage_service=StorageService())

    # Candidate 2 never applied to Org A
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    with pytest.raises((AuthorizationException, EntityNotFoundException)) as exc_info:
        await applicant_service.get_candidate_details(
            db, tenant_id=s["tenant_a_id"], candidate_id=s["cand_user_2"].id
        )
    assert "not accessible" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_tenant_isolation_candidate_facing_apis_never_expose_internal_data(acceptance_fixture):
    """Candidate-facing timeline queries strip all internal notes and scorecards."""
    s = acceptance_fixture
    db = AsyncMock()
    review_service = HrReviewService()
    tenant_id = s["tenant_a_id"]
    cand_id = s["cand_user_1"].id

    app = JobApplication(id=generate_uuid7(), tenant_id=tenant_id, candidate_id=cand_id, status="screening", applied_at=utc_now())
    job = Job(id=generate_uuid7(), tenant_id=tenant_id, title="Platform Lead", department="Eng")

    # DB mocks
    db.execute = AsyncMock(side_effect=[
        # Candidate check
        MagicMock(scalar_one_or_none=MagicMock(return_value=app.id)),
        # Applications query
        MagicMock(all=MagicMock(return_value=[(app, job)])),
        # Stage history query
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])

    # Candidate viewer requests timeline (is_internal_viewer = False)
    timeline = await review_service.get_candidate_timeline(
        db, tenant_id, cand_id, app.id, is_internal_viewer=False
    )
    for event in timeline.events:
        assert event.is_internal is False
        assert "note" not in event.event_type
        assert "review" not in event.event_type
        assert "task" not in event.event_type


# ==============================================================================
# SECTION 3: APPLICATION SECURITY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_security_idor_resume_download_protection(acceptance_fixture):
    """IDOR Protection: Requesting resume download URL across tenant boundary raises EntityNotFoundException."""
    s = acceptance_fixture
    db = AsyncMock()
    storage = StorageService()
    applicant_service = HrApplicantService(storage_service=storage)

    # Application belongs to Tenant A
    app_a = JobApplication(id=generate_uuid7(), tenant_id=s["tenant_a_id"])

    # Tenant B tries to download Tenant A's resume by guessing app_a.id -> scalar_one_or_none returns None
    mock_app_query = MagicMock()
    mock_app_query.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_app_query)

    with pytest.raises(EntityNotFoundException):
        await applicant_service.get_resume_signed_url(
            db=db,
            tenant_id=s["tenant_b_id"],
            application_id=app_a.id,
            actor_user_id=s["recruiter_b"].id,
        )


@pytest.mark.asyncio
async def test_security_rbac_recruiter_self_approval_blocked(acceptance_fixture):
    """Separation of Duties: Lead recruiter is strictly prohibited from approving their own job requisition."""
    s = acceptance_fixture
    db = AsyncMock()
    lifecycle_service = HrJobLifecycleService()

    job = Job(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        title="Software Engineer",
        status="pending_approval",
        recruiter_id=s["recruiter_a"].id,
    )
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=job)))

    with pytest.raises(AuthorizationException) as exc_info:
        await lifecycle_service.execute_transition(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=job.id,
            user_id=s["recruiter_a"].id,
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="approve"),
        )
    assert "not permit" in str(exc_info.value).lower() or "separation of duties" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_security_unauthorized_job_publication_blocked(acceptance_fixture):
    """Unapproved draft jobs cannot be published directly without approval."""
    s = acceptance_fixture
    db = AsyncMock()
    lifecycle_service = HrJobLifecycleService()

    # Job is in 'draft' status
    job = Job(id=generate_uuid7(), tenant_id=s["tenant_a_id"], title="Backend Dev", status="draft")
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=job)))

    with pytest.raises(ConflictException) as exc_info:
        await lifecycle_service.execute_transition(
            db=db,
            tenant_id=s["tenant_a_id"],
            job_id=job.id,
            user_id=s["admin_a"].id,
            user_roles=["admin"],
            request=JobLifecycleActionRequest(action="publish"),
        )
    assert "not permitted" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_security_unauthorized_stage_skipping_blocked(acceptance_fixture):
    """Illegal stage transition (e.g. from withdrawn to hired) is rejected by pipeline FSM."""
    s = acceptance_fixture
    db = AsyncMock()
    pipeline_service = HrPipelineService()

    app = JobApplication(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        status="withdrawn",
        withdrawn_at=utc_now(),
    )
    db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=app)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ])

    with pytest.raises(ConflictException) as exc_info:
        await pipeline_service.transition_stage(
            db=db,
            tenant_id=s["tenant_a_id"],
            application_id=app.id,
            target_stage="hired",
            actor_id=s["recruiter_a"].id,
            actor_role="recruiter",
            actor_name="Alice Recruiter",
        )
    assert "withdrawn" in str(exc_info.value).lower() or exc_info.value.error_code == "APPLICATION_WITHDRAWN"


@pytest.mark.asyncio
async def test_security_sql_injection_and_xss_sanitization(acceptance_fixture):
    """Validates that SQL injection attacks and stored XSS attempts are safely handled as literal strings."""
    s = acceptance_fixture
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    review_service = HrReviewService()
    tenant_id = s["tenant_a_id"]

    # Injected payloads
    sqli_payload = "'; DROP TABLE candidate_internal_notes; --"
    xss_payload = "<script>alert('XSS Attack');</script>"

    # 1. Internal Note with SQLi and XSS content
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=uuid4())))
    note_req = CreateInternalNoteRequest(
        content=f"{sqli_payload} {xss_payload}",
        category="general",
    )
    note = await review_service.add_internal_note(
        db=db,
        tenant_id=tenant_id,
        candidate_id=s["cand_user_1"].id,
        author_id=s["recruiter_a"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        request=note_req,
    )
    # Stored as literal text, not executed
    assert sqli_payload in note.content
    assert xss_payload in note.content

    # 2. Task with SQLi title
    task_req = CreateRecruitmentTaskRequest(
        title=f"Check candidate {sqli_payload}",
        description=xss_payload,
        task_type="general",
    )
    task = await review_service.create_task(
        db=db,
        tenant_id=tenant_id,
        candidate_id=s["cand_user_1"].id,
        creator_id=s["recruiter_a"].id,
        creator_name="Alice Recruiter",
        request=task_req,
    )
    assert sqli_payload in task.title
    assert xss_payload in task.description


@pytest.mark.asyncio
async def test_security_task_assignee_cross_tenant_blocked(acceptance_fixture):
    """Recruitment task assignee must belong to the organization tenant; assigning a cross-tenant user is forbidden."""
    s = acceptance_fixture
    db = AsyncMock()
    review_service = HrReviewService()
    tenant_id = s["tenant_a_id"]

    # Candidate belongs to Org A
    db.execute = AsyncMock(side_effect=[
        # Candidate check
        MagicMock(scalar_one_or_none=MagicMock(return_value=uuid4())),
        # Assignee membership check -> Org B recruiter does not belong to Org A
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ])

    task_req = CreateRecruitmentTaskRequest(
        title="Conduct initial phone screen",
        assignee_id=s["recruiter_b"].id, # User from Org B!
    )
    with pytest.raises((AuthorizationException, ValidationException)) as exc_info:
        await review_service.create_task(
            db=db,
            tenant_id=tenant_id,
            candidate_id=s["cand_user_1"].id,
            creator_id=s["recruiter_a"].id,
            creator_name="Alice Recruiter",
            request=task_req,
        )
    assert "Assignee is not an active member of this organization" in str(exc_info.value) or getattr(exc_info.value, "code", "") == "USER_NOT_ORGANIZATION_MEMBER"
