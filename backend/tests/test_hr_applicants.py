"""Unit and integration tests for HR Applicant and Candidate Management (Step 4.2.5).

Tests listing, filtering, search, candidate details, cross-tenant isolation,
resume access presigned URLs, candidate comparison, and bulk recruiter assignment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.base import generate_uuid7
from app.core.errors import AuthorizationException, EntityNotFoundException
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
from app.modules.hr.applicant_service import HrApplicantService, calculate_experience_years
from app.modules.jobs.models import Job, JobApplication
from app.modules.organizations.models import OrganizationMembership


@pytest.fixture
def mock_storage_service() -> StorageService:
    service = StorageService()
    service.generate_presigned_download_url = MagicMock(
        return_value="https://s3.mock.domain/bucket/resumes/candidate1.pdf?sig=valid_token&expires=900"
    )
    return service


@pytest.fixture
def test_setup():
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    recruiter_a = User(
        id=generate_uuid7(),
        email="recruiter.a@acme.com",
        password_hash="hash",
        first_name="Alice",
        last_name="Recruiter",
        is_active=True,
    )
    hm_a = User(
        id=generate_uuid7(),
        email="hm.a@acme.com",
        password_hash="hash",
        first_name="Bob",
        last_name="HiringMgr",
        is_active=True,
    )

    job_a1 = Job(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        title="Senior Python Platform Engineer",
        slug="sr-python-eng-1234",
        department="Engineering",
        location="Austin, TX",
        remote_type="hybrid",
        employment_type="full_time",
        experience_level="senior",
        description="Build scalable distributed cloud services.",
        skills_required=["Python", "FastAPI", "PostgreSQL", "Docker"],
        status="published",
        visibility="public",
        recruiter_id=recruiter_a.id,
        hiring_manager_id=hm_a.id,
    )
    job_a1.recruiter = recruiter_a
    job_a1.hiring_manager = hm_a

    job_b1 = Job(
        id=generate_uuid7(),
        tenant_id=tenant_b_id,
        title="Lead DevOps Architect",
        slug="lead-devops-5678",
        department="Infrastructure",
        location="New York, NY",
        remote_type="remote",
        employment_type="full_time",
        experience_level="lead",
        description="Architect multi-cloud infrastructure.",
        skills_required=["Kubernetes", "Terraform", "AWS"],
        status="published",
        visibility="public",
    )

    # Candidate 1 (applied to Job A1)
    cand_1 = User(
        id=generate_uuid7(),
        email="candidate.one@example.com",
        password_hash="hash",
        first_name="Jane",
        last_name="Doe",
        is_active=True,
    )
    profile_1 = CandidateUserProfile(
        user_id=cand_1.id,
        headline="Full Stack Cloud Developer",
        bio="Passionate engineer with 4+ years of cloud experience.",
        location_city="Austin",
        location_country="United States",
        self_declared_skills=["Python", "FastAPI", "React", "Docker"],
    )
    resume_1 = CandidateResume(
        id=generate_uuid7(),
        user_id=cand_1.id,
        storage_key=f"tenants/{tenant_a_id}/documents/2026/11/resume_1.pdf",
        filename="Jane_Doe_Resume_2026.pdf",
        file_size_bytes=1048576,
        mime_type="application/pdf",
        content_sha256="sha256_mock_hash_1",
        skills_extracted=["Python", "PostgreSQL", "Kafka"],
    )
    app_1 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_1.id,
        resume_id=resume_1.id,
        resume_snapshot_sha256="sha256_mock_hash_1",
        status="in_screening",
        candidate_status="under_review",
        applied_at=datetime.now(UTC),
        timeline=[
            {
                "status": "submitted",
                "changed_at": datetime.now(UTC).isoformat(),
                "note": "Application submitted",
                "is_internal": False,
            },
            {
                "status": "in_screening",
                "changed_at": datetime.now(UTC).isoformat(),
                "note": "Candidate moved to screening review",
                "is_internal": True,
            },
        ],
    )

    # Candidate 2 (applied to Job A1)
    cand_2 = User(
        id=generate_uuid7(),
        email="candidate.two@example.com",
        password_hash="hash",
        first_name="John",
        last_name="Smith",
        is_active=True,
    )
    profile_2 = CandidateUserProfile(
        user_id=cand_2.id,
        headline="Senior Backend Engineer",
        bio="Distributed systems engineer.",
        location_city="San Francisco",
        location_country="United States",
        self_declared_skills=["Python", "Go", "PostgreSQL", "Kubernetes"],
    )
    app_2 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_2.id,
        resume_id=None,
        resume_snapshot_sha256="sha256_mock_hash_2",
        status="submitted",
        candidate_status="submitted",
        applied_at=datetime.now(UTC),
    )

    # Candidate 3 (applied to Job B1 under Tenant B)
    cand_3 = User(
        id=generate_uuid7(),
        email="candidate.three@othercorp.com",
        password_hash="hash",
        first_name="Carlos",
        last_name="Santos",
        is_active=True,
    )
    app_3 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_b_id,
        job_id=job_b1.id,
        candidate_id=cand_3.id,
        resume_snapshot_sha256="sha256_mock_hash_3",
        status="submitted",
        candidate_status="submitted",
        applied_at=datetime.now(UTC),
    )

    return {
        "tenant_a_id": tenant_a_id,
        "tenant_b_id": tenant_b_id,
        "recruiter_a": recruiter_a,
        "hm_a": hm_a,
        "job_a1": job_a1,
        "job_b1": job_b1,
        "cand_1": cand_1,
        "profile_1": profile_1,
        "resume_1": resume_1,
        "app_1": app_1,
        "cand_2": cand_2,
        "profile_2": profile_2,
        "app_2": app_2,
        "cand_3": cand_3,
        "app_3": app_3,
    }


def test_experience_years_calculation():
    """Verify cumulative professional experience parsing and calculation."""
    exps = [
        CandidateExperience(
            id=generate_uuid7(),
            user_id=generate_uuid7(),
            job_title="Software Engineer",
            company_name="Tech Corp",
            start_date="2020-01",
            end_date="2022-01",
            is_current=False,
        ),
        CandidateExperience(
            id=generate_uuid7(),
            user_id=generate_uuid7(),
            job_title="Senior Engineer",
            company_name="Cloud Corp",
            start_date="2022-01",
            end_date="2024-01",
            is_current=False,
        ),
    ]
    years = calculate_experience_years(exps)
    assert years == 4.0


@pytest.mark.asyncio
async def test_applicant_listing_tenant_scoped(test_setup, mock_storage_service):
    """Verify applicant listing queries strictly tenant-authorized records with metadata."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()

    # Mock count query
    count_res = MagicMock()
    count_res.scalar.return_value = 2

    # Mock rows query: returns app_1 and app_2
    row_1 = (
        setup["app_1"],
        setup["job_a1"],
        setup["cand_1"],
        setup["profile_1"],
        setup["resume_1"],
    )
    row_2 = (
        setup["app_2"],
        setup["job_a1"],
        setup["cand_2"],
        setup["profile_2"],
        None,
    )
    rows_res = MagicMock()
    rows_res.all.return_value = [row_1, row_2]

    # Mock experiences query
    exp_res = MagicMock()
    mock_exp = CandidateExperience(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        job_title="Full Stack Developer",
        company_name="StartUp Inc",
        start_date="2021-01",
        end_date="2024-01",
        is_current=False,
        skills=["Python", "FastAPI"],
    )
    exp_res.scalars.return_value.all.return_value = [mock_exp]

    mock_db.execute.side_effect = [count_res, rows_res, exp_res]

    response = await service.list_applicants(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        page=1,
        page_size=20,
    )

    assert response.total == 2
    assert len(response.items) == 2
    assert response.items[0].candidate_name == "Jane Doe"
    assert response.items[0].job_title == "Senior Python Platform Engineer"
    assert response.items[0].resume_available is True
    assert "Python" in response.items[0].skills
    assert response.items[0].experience_years == 3.0

    assert response.items[1].candidate_name == "John Smith"
    assert response.items[1].resume_available is True  # has resume_snapshot_sha256


@pytest.mark.asyncio
async def test_candidate_details_retrieval_and_application_context(test_setup, mock_storage_service):
    """Verify authorized candidate profile retrieval with portfolio, timelines, and org history."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()

    # 1. Auth check
    auth_res = MagicMock()
    auth_res.scalar_one_or_none.return_value = setup["app_1"].id

    # 2. User & Profile
    user_res = MagicMock()
    user_res.scalar_one_or_none.return_value = setup["cand_1"]
    prof_res = MagicMock()
    prof_res.scalar_one_or_none.return_value = setup["profile_1"]

    # 3. Portfolio records
    exp_res = MagicMock()
    mock_exp = CandidateExperience(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        job_title="Senior Developer",
        company_name="Acme Tech",
        start_date="2020-01",
        end_date="2023-01",
        is_current=False,
        skills=["Python", "Docker"],
    )
    exp_res.scalars.return_value.all.return_value = [mock_exp]

    edu_res = MagicMock()
    mock_edu = CandidateEducation(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        institution="UT Austin",
        degree="B.S. Computer Science",
        field_of_study="Computer Science",
        start_year=2016,
        end_year=2020,
    )
    edu_res.scalars.return_value.all.return_value = [mock_edu]

    cert_res = MagicMock()
    mock_cert = CandidateCertification(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services",
        issue_date="2023",
    )
    cert_res.scalars.return_value.all.return_value = [mock_cert]

    proj_res = MagicMock()
    mock_proj = CandidateProject(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        title="Async Task Engine",
        description="High throughput queue engine",
        skills=["Go", "Redis"],
    )
    proj_res.scalars.return_value.all.return_value = [mock_proj]

    lang_res = MagicMock()
    mock_lang = CandidateLanguage(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        language="English",
        proficiency="native",
    )
    lang_res.scalars.return_value.all.return_value = [mock_lang]

    # 4. Org application history
    hist_res = MagicMock()
    hist_res.all.return_value = [(setup["app_1"], setup["job_a1"])]

    # 5. Target application context
    target_res = MagicMock()
    target_res.first.return_value = (setup["app_1"], setup["job_a1"], setup["resume_1"])

    mock_db.execute.side_effect = [
        auth_res,
        user_res,
        prof_res,
        exp_res,
        edu_res,
        cert_res,
        proj_res,
        lang_res,
        hist_res,
        target_res,
    ]

    details = await service.get_candidate_details(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        candidate_id=setup["cand_1"].id,
        application_id=setup["app_1"].id,
    )

    assert details.full_name == "Jane Doe"
    assert details.email == "candidate.one@example.com"
    assert details.headline == "Full Stack Cloud Developer"
    assert len(details.experiences) == 1
    assert len(details.educations) == 1
    assert len(details.certifications) == 1
    assert len(details.projects) == 1
    assert len(details.languages) == 1
    assert len(details.organization_application_history) == 1

    # Verify timeline separation
    assert details.current_application is not None
    assert len(details.current_application.candidate_timeline) == 1
    assert details.current_application.candidate_timeline[0].status == "submitted"
    assert len(details.current_application.internal_timeline) == 1
    assert details.current_application.internal_timeline[0].status == "in_screening"


@pytest.mark.asyncio
async def test_cross_tenant_candidate_privacy_blocked(test_setup, mock_storage_service):
    """Verify recruiter from Org A cannot access Candidate 3 who only applied to Org B."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()
    auth_res = MagicMock()
    auth_res.scalar_one_or_none.return_value = None  # No application under Tenant A!
    mock_db.execute.return_value = auth_res

    with pytest.raises(AuthorizationException) as exc_info:
        await service.get_candidate_details(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            candidate_id=setup["cand_3"].id,
        )

    assert exc_info.value.code == "CANDIDATE_ACCESS_FORBIDDEN"


@pytest.mark.asyncio
async def test_resume_presigned_download_url_and_audit_logging(test_setup, mock_storage_service):
    """Verify short-lived presigned URL generation with strict tenant check and audit logging."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_1"]

    res_res = MagicMock()
    res_res.scalar_one_or_none.return_value = setup["resume_1"]

    mock_db.execute.side_effect = [app_res, res_res]

    actor_id = setup["recruiter_a"].id
    res = await service.get_resume_signed_url(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_id=setup["app_1"].id,
        actor_user_id=actor_id,
    )

    assert res.download_url.startswith("https://s3.mock.domain/")
    assert res.expires_in_seconds == 900
    assert res.filename == "Jane_Doe_Resume_2026.pdf"
    assert res.content_sha256 == "sha256_mock_hash_1"

    # Verify audit metadata updated
    audit = setup["app_1"].audit_metadata
    assert "resume_access_history" in audit
    assert audit["resume_access_history"][-1]["actor_id"] == str(actor_id)

    # Verify internal timeline event added
    assert any(
        e.get("is_internal") and e.get("status") == "resume_viewed"
        for e in setup["app_1"].timeline
    )
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_access_cross_tenant_rejected(test_setup, mock_storage_service):
    """Verify recruiter from Tenant A cannot access resume of application in Tenant B."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()
    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = None  # Application not found under Tenant A
    mock_db.execute.return_value = app_res

    with pytest.raises(EntityNotFoundException):
        await service.get_resume_signed_url(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_3"].id,  # Org B application
            actor_user_id=setup["recruiter_a"].id,
        )


@pytest.mark.asyncio
async def test_candidate_comparison_matrix(test_setup, mock_storage_service):
    """Verify comparative evaluation matrix calculation across multiple candidates."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()

    rows = [
        (
            setup["app_1"],
            setup["job_a1"],
            setup["cand_1"],
            setup["profile_1"],
            setup["resume_1"],
        ),
        (
            setup["app_2"],
            setup["job_a1"],
            setup["cand_2"],
            setup["profile_2"],
            None,
        ),
    ]
    apps_res = MagicMock()
    apps_res.all.return_value = rows

    exp_res = MagicMock()
    mock_exp_1 = CandidateExperience(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        job_title="Platform Engineer",
        company_name="Cloud Corp",
        start_date="2020-01",
        end_date="2024-01",
        is_current=True,
        skills=["Python", "FastAPI"],
    )
    exp_res.scalars.return_value.all.return_value = [mock_exp_1]

    edu_res = MagicMock()
    mock_edu_1 = CandidateEducation(
        id=generate_uuid7(),
        user_id=setup["cand_1"].id,
        institution="MIT",
        degree="Master of Science",
        field_of_study="Computer Science",
    )
    edu_res.scalars.return_value.all.return_value = [mock_edu_1]

    mock_db.execute.side_effect = [apps_res, exp_res, edu_res]

    comp = await service.compare_candidates(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_ids=[setup["app_1"].id, setup["app_2"].id],
    )

    assert comp.job_title == "Senior Python Platform Engineer"
    assert len(comp.candidates) == 2

    cand1_comp = comp.candidates[0]
    assert cand1_comp.candidate_name == "Jane Doe"
    assert "Python" in cand1_comp.matching_skills
    assert cand1_comp.match_percentage > 0.0
    assert cand1_comp.highest_education == "Master of Science"


@pytest.mark.asyncio
async def test_bulk_recruiter_assignment(test_setup, mock_storage_service):
    """Verify bulk recruiter assignment with organization membership validation."""
    setup = test_setup
    service = HrApplicantService(storage_service=mock_storage_service)

    mock_db = AsyncMock()

    # Recruiter membership verified
    recruiter_mem = OrganizationMembership(
        id=generate_uuid7(),
        user_id=setup["recruiter_a"].id,
        tenant_id=setup["tenant_a_id"],
        role_id=generate_uuid7(),
        is_active=True,
    )
    mem_res = MagicMock()
    mem_res.first.return_value = (recruiter_mem, setup["recruiter_a"])

    # Applications query
    apps_res = MagicMock()
    apps_res.scalars.return_value.all.return_value = [setup["app_1"], setup["app_2"]]

    mock_db.execute.side_effect = [mem_res, apps_res]

    res = await service.bulk_assign_recruiter(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_ids=[setup["app_1"].id, setup["app_2"].id],
        recruiter_id=setup["recruiter_a"].id,
        actor_id=setup["hm_a"].id,
    )

    assert res.updated_count == 2
    assert res.recruiter_name == "Alice Recruiter"
    mock_db.commit.assert_awaited_once()
