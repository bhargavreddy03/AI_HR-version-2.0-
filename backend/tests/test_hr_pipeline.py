"""Unit and integration tests for Recruitment Pipeline and Stage Management (Step 4.2.6).

Tests FSM transition rules, Kanban board grouping, optimistic locking,
mandatory rejection reasons, withdrawal protection, role restrictions, and bulk moves.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.base import generate_uuid7
from app.core.errors import (
    AppException,
    AuthorizationException,
    ConflictException,
    EntityNotFoundException,
)
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.hr.pipeline_service import HrPipelineService
from app.modules.jobs.models import (
    ApplicationStageHistory,
    CandidateFacingStatus,
    Job,
    JobApplication,
)


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
        status="published",
        visibility="public",
        recruiter_id=recruiter_a.id,
        hiring_manager_id=hm_a.id,
    )
    job_a1.recruiter = recruiter_a

    # Candidate 1: in applied stage
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
        self_declared_skills=["Python", "FastAPI", "Docker"],
    )
    app_1 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_1.id,
        resume_snapshot_sha256="sha256_mock_1",
        status="applied",
        candidate_status="submitted",
        stage_version=1,
        applied_at=datetime.now(UTC),
        timeline=[],
    )

    # Candidate 2: in interview stage
    cand_2 = User(
        id=generate_uuid7(),
        email="candidate.two@example.com",
        password_hash="hash",
        first_name="John",
        last_name="Smith",
        is_active=True,
    )
    app_2 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_2.id,
        resume_snapshot_sha256="sha256_mock_2",
        status="interview",
        candidate_status="interview_stage",
        stage_version=2,
        applied_at=datetime.now(UTC),
        timeline=[],
    )

    # Candidate 3: withdrawn
    cand_3 = User(
        id=generate_uuid7(),
        email="candidate.three@example.com",
        password_hash="hash",
        first_name="Sara",
        last_name="Withdrawn",
        is_active=True,
    )
    app_3 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_3.id,
        resume_snapshot_sha256="sha256_mock_3",
        status="withdrawn",
        candidate_status="withdrawn",
        stage_version=3,
        applied_at=datetime.now(UTC),
        timeline=[],
    )

    # Candidate 4: hired
    cand_4 = User(
        id=generate_uuid7(),
        email="candidate.four@example.com",
        password_hash="hash",
        first_name="Henry",
        last_name="Hired",
        is_active=True,
    )
    app_4 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_a1.id,
        candidate_id=cand_4.id,
        resume_snapshot_sha256="sha256_mock_4",
        status="hired",
        candidate_status="offer_stage",
        stage_version=4,
        applied_at=datetime.now(UTC),
        timeline=[],
    )

    # Candidate 5 under Tenant B (cross-tenant test)
    app_b = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_b_id,
        job_id=generate_uuid7(),
        candidate_id=generate_uuid7(),
        resume_snapshot_sha256="sha256_mock_b",
        status="applied",
        candidate_status="submitted",
        stage_version=1,
        applied_at=datetime.now(UTC),
    )

    return {
        "tenant_a_id": tenant_a_id,
        "tenant_b_id": tenant_b_id,
        "recruiter_a": recruiter_a,
        "hm_a": hm_a,
        "job_a1": job_a1,
        "cand_1": cand_1,
        "profile_1": profile_1,
        "app_1": app_1,
        "cand_2": cand_2,
        "app_2": app_2,
        "cand_3": cand_3,
        "app_3": app_3,
        "cand_4": cand_4,
        "app_4": app_4,
        "app_b": app_b,
    }


@pytest.mark.asyncio
async def test_get_configured_stages_default_and_custom(test_setup):
    """Verify loading default 11 workflow stages and tenant-configured custom stages."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    # 1. Default fallback when organization custom stages is None
    org_res_default = MagicMock()
    org_res_default.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = org_res_default

    stages = await service.get_configured_stages(mock_db, setup["tenant_a_id"])
    assert len(stages) == 11
    assert stages[0].id == "applied"
    assert stages[2].id == "screening"
    assert stages[-1].id == "withdrawn"

    # 2. Custom stages configured on organization
    custom_stages = [
        {"id": "applied", "label": "Applied", "order": 1, "is_terminal": False},
        {"id": "screening", "label": "Technical Screening", "order": 2, "is_terminal": False},
        {"id": "hired", "label": "Hired", "order": 3, "is_terminal": True},
    ]
    org_res_custom = MagicMock()
    org_res_custom.scalar_one_or_none.return_value = custom_stages
    mock_db.execute.return_value = org_res_custom

    custom_res = await service.get_configured_stages(mock_db, setup["tenant_a_id"])
    assert len(custom_res) == 3
    assert custom_res[1].label == "Technical Screening"


@pytest.mark.asyncio
async def test_pipeline_board_grouped_by_stage_with_cards(test_setup):
    """Verify Kanban pipeline board groups applications by normalized stage into columns."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    # Org stages: default
    org_res = MagicMock()
    org_res.scalar_one_or_none.return_value = None

    # Rows: app_1 (applied) and app_2 (interview)
    row_1 = (setup["app_1"], setup["job_a1"], setup["cand_1"], setup["profile_1"], None)
    row_2 = (setup["app_2"], setup["job_a1"], setup["cand_2"], None, None)
    rows_res = MagicMock()
    rows_res.all.return_value = [row_1, row_2]

    mock_db.execute.side_effect = [org_res, rows_res]

    board = await service.get_pipeline_board(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        job_id=setup["job_a1"].id,
    )

    assert board.total_candidates == 2
    applied_col = next(s for s in board.stages if s.id == "applied")
    interview_col = next(s for s in board.stages if s.id == "interview")

    assert applied_col.count == 1
    assert applied_col.cards[0].candidate_name == "Jane Doe"
    assert applied_col.cards[0].skills == ["Docker", "FastAPI", "Python"]

    assert interview_col.count == 1
    assert interview_col.cards[0].candidate_name == "John Smith"


@pytest.mark.asyncio
async def test_valid_stage_transition_and_history_creation(test_setup):
    """Verify advancing from applied to screening creates history and maps candidate status."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_1"]
    mock_db.execute.return_value = app_res

    res = await service.transition_stage(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_id=setup["app_1"].id,
        target_stage="screening",
        actor_id=setup["recruiter_a"].id,
        actor_role="recruiter",
        actor_name="Alice Recruiter",
        expected_stage_version=1,
    )

    assert res.previous_stage == "applied"
    assert res.new_stage == "screening"
    assert res.stage_version == 2
    assert res.candidate_status == CandidateFacingStatus.IN_SCREENING.value
    assert setup["app_1"].status == "screening"
    assert setup["app_1"].candidate_status == "in_screening"

    # Verify stage history record added
    mock_db.add.assert_called_once()
    history_entry = mock_db.add.call_args[0][0]
    assert isinstance(history_entry, ApplicationStageHistory)
    assert history_entry.previous_stage == "applied"
    assert history_entry.new_stage == "screening"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_prohibited_stage_transition_rejected(test_setup):
    """Verify illegal transitions (e.g. applied directly to offer) are blocked by FSM rules."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_1"]  # status = "applied"
    mock_db.execute.return_value = app_res

    with pytest.raises(ConflictException) as exc_info:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_1"].id,
            target_stage="offer",  # Illegal from applied
            actor_id=setup["hm_a"].id,
            actor_role="hiring_manager",
            actor_name="Bob Manager",
        )

    assert exc_info.value.code == "INVALID_STAGE_TRANSITION"


@pytest.mark.asyncio
async def test_mandatory_rejection_reason_enforcement(test_setup):
    """Verify rejection without reason is rejected, and with reason succeeds."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_1"]
    mock_db.execute.return_value = app_res

    # 1. Empty reason -> rejected
    with pytest.raises(AppException) as exc_info:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_1"].id,
            target_stage="rejected",
            actor_id=setup["recruiter_a"].id,
            actor_role="recruiter",
            actor_name="Alice Recruiter",
            reason="",  # Missing!
        )
    assert exc_info.value.code == "REJECTION_REASON_REQUIRED"

    # 2. Valid reason -> succeeds
    res = await service.transition_stage(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_id=setup["app_1"].id,
        target_stage="rejected",
        actor_id=setup["recruiter_a"].id,
        actor_role="recruiter",
        actor_name="Alice Recruiter",
        reason="Does not meet minimum 5 years distributed systems experience requirement",
    )
    assert res.new_stage == "rejected"
    assert res.candidate_status == CandidateFacingStatus.NOT_SELECTED.value
    assert (
        setup["app_1"].rejection_reason
        == "Does not meet minimum 5 years distributed systems experience requirement"
    )


@pytest.mark.asyncio
async def test_withdrawn_and_hired_protection(test_setup):
    """Verify withdrawn candidates cannot be transitioned, and hired is a terminal state."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    # 1. Withdrawn application protection
    app_res_withdrawn = MagicMock()
    app_res_withdrawn.scalar_one_or_none.return_value = setup["app_3"]
    mock_db.execute.return_value = app_res_withdrawn

    with pytest.raises(ConflictException) as exc_info:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_3"].id,
            target_stage="screening",
            actor_id=setup["recruiter_a"].id,
            actor_role="recruiter",
            actor_name="Alice Recruiter",
        )
    assert exc_info.value.code == "APPLICATION_WITHDRAWN"

    # 2. Hired terminal state protection
    app_res_hired = MagicMock()
    app_res_hired.scalar_one_or_none.return_value = setup["app_4"]
    mock_db.execute.return_value = app_res_hired

    with pytest.raises(ConflictException) as exc_info2:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_4"].id,
            target_stage="interview",
            actor_id=setup["hm_a"].id,
            actor_role="hiring_manager",
            actor_name="Bob Manager",
        )
    assert exc_info2.value.code == "APPLICATION_HIRED_TERMINAL"


@pytest.mark.asyncio
async def test_optimistic_concurrency_conflict(test_setup):
    """Verify mismatched expected_stage_version raises CONCURRENT_UPDATE_CONFLICT."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_1"]  # stage_version = 1
    mock_db.execute.return_value = app_res

    with pytest.raises(ConflictException) as exc_info:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_1"].id,
            target_stage="screening",
            actor_id=setup["recruiter_a"].id,
            actor_role="recruiter",
            actor_name="Alice Recruiter",
            expected_stage_version=99,  # Mismatch!
        )

    assert exc_info.value.code == "CONCURRENT_UPDATE_CONFLICT"


@pytest.mark.asyncio
async def test_offer_and_hired_role_restrictions(test_setup):
    """Verify regular recruiter cannot unilaterally move candidates to offer or hired without manager role."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = setup["app_2"]  # in interview stage
    mock_db.execute.return_value = app_res

    # Recruiter alone -> blocked
    with pytest.raises(AuthorizationException) as exc_info:
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_2"].id,
            target_stage="offer",
            actor_id=setup["recruiter_a"].id,
            actor_role="recruiter",  # Not hiring manager or org admin
            actor_name="Alice Recruiter",
        )

    assert exc_info.value.code == "INSUFFICIENT_STAGE_PERMISSIONS"


@pytest.mark.asyncio
async def test_bulk_stage_move_evaluates_rules_per_application(test_setup):
    """Verify bulk move processes eligible applications and safely skips ineligible ones."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    # Query returns app_1 (applied) and app_3 (withdrawn)
    rows = [
        (setup["app_1"], setup["cand_1"]),
        (setup["app_3"], setup["cand_3"]),
    ]
    apps_res = MagicMock()
    apps_res.all.return_value = rows
    mock_db.execute.return_value = apps_res

    res = await service.bulk_stage_move(
        db=mock_db,
        tenant_id=setup["tenant_a_id"],
        application_ids=[setup["app_1"].id, setup["app_3"].id],
        target_stage="screening",
        actor_id=setup["recruiter_a"].id,
        actor_role="recruiter",
        actor_name="Alice Recruiter",
    )

    assert res.total_requested == 2
    assert res.updated_count == 1
    assert setup["app_1"].id in res.updated_ids
    assert res.skipped_count == 1
    assert res.skipped[0].application_id == setup["app_3"].id
    assert "withdrawn" in res.skipped[0].reason
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cross_tenant_pipeline_isolation(test_setup):
    """Verify recruiter from Tenant A cannot transition application from Tenant B."""
    setup = test_setup
    service = HrPipelineService()
    mock_db = AsyncMock()

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = None  # Not found under Tenant A
    mock_db.execute.return_value = app_res

    with pytest.raises(EntityNotFoundException):
        await service.transition_stage(
            db=mock_db,
            tenant_id=setup["tenant_a_id"],
            application_id=setup["app_b"].id,  # Org B application
            target_stage="screening",
            actor_id=setup["recruiter_a"].id,
            actor_role="recruiter",
            actor_name="Alice Recruiter",
        )
