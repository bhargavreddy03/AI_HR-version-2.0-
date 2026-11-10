"""Unit and integration tests for Candidate Review and HR Collaboration (Step 4.2.8).

Tests internal notes authorship & confidentiality, scorecards, recruitment follow-up tasks,
unified activity timeline visibility separation, and cross-tenant privacy boundaries.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    AuthorizationException,
    ValidationException,
)
from app.modules.auth.models import User
from app.modules.hr.review_schemas import (
    CreateInternalNoteRequest,
    CreateRecruitmentTaskRequest,
    SubmitReviewFeedbackRequest,
    UpdateInternalNoteRequest,
    UpdateRecruitmentTaskRequest,
)
from app.modules.hr.review_service import HrReviewService
from app.modules.jobs.models import (
    ApplicationStageHistory,
    CandidateInternalNote,
    CandidateRecruitmentTask,
    CandidateReviewFeedback,
    Job,
    JobApplication,
)


@pytest.fixture
def review_setup():
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

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
    hm_user = User(
        id=generate_uuid7(),
        email="hm@acme.com",
        password_hash="hash",
        first_name="Carol",
        last_name="Manager",
        is_active=True,
    )
    candidate_user = User(
        id=generate_uuid7(),
        email="candidate@example.com",
        password_hash="hash",
        first_name="Jane",
        last_name="Developer",
        is_active=True,
    )
    external_user = User(
        id=generate_uuid7(),
        email="external@other.com",
        password_hash="hash",
        first_name="External",
        last_name="Stranger",
        is_active=True,
    )

    job_1 = Job(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        title="Senior Cloud Architect",
        slug="sr-cloud-arch-1",
        department="Platform",
        location="Austin, TX",
        remote_type="remote",
        employment_type="full_time",
        description="Senior cloud architecture role",
        status="published",
        vacancies_count=1,
        recruiter_id=recruiter_1.id,
        hiring_manager_id=hm_user.id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    app_1 = JobApplication(
        id=generate_uuid7(),
        tenant_id=tenant_a_id,
        job_id=job_1.id,
        candidate_id=candidate_user.id,
        resume_snapshot_sha256="hash123",
        status="screening",
        candidate_status="under_review",
        applied_at=utc_now(),
    )
    app_1.job = job_1

    return {
        "tenant_a_id": tenant_a_id,
        "tenant_b_id": tenant_b_id,
        "admin_user": admin_user,
        "recruiter_1": recruiter_1,
        "recruiter_2": recruiter_2,
        "hm_user": hm_user,
        "candidate_user": candidate_user,
        "external_user": external_user,
        "job_1": job_1,
        "app_1": app_1,
    }


@pytest.mark.asyncio
async def test_add_internal_note_success_and_can_edit(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    # db.execute mock for _verify_candidate_belongs_to_tenant
    mock_auth_res = MagicMock()
    mock_auth_res.scalar_one_or_none.return_value = s["app_1"].id
    db.execute.return_value = mock_auth_res

    db.get.return_value = s["app_1"]

    added_objects = []
    db.add = MagicMock(side_effect=lambda o: added_objects.append(o))

    req = CreateInternalNoteRequest(
        application_id=s["app_1"].id,
        content="Candidate demonstrated strong knowledge of distributed systems and Kubernetes.",
        category="screening",
        is_confidential=False,
    )

    resp = await service.add_internal_note(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        author_id=s["recruiter_1"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        request=req,
    )

    assert resp.candidate_id == s["candidate_user"].id
    assert resp.application_id == s["app_1"].id
    assert resp.author_name == "Alice Recruiter"
    assert resp.category == "screening"
    assert resp.can_edit is True
    assert len(added_objects) == 1
    assert isinstance(added_objects[0], CandidateInternalNote)


@pytest.mark.asyncio
async def test_internal_note_confidentiality_isolation(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    # Verify candidate returns active app
    mock_auth_res = MagicMock()
    mock_auth_res.scalar_one_or_none.return_value = s["app_1"].id

    # Notes query returns 2 notes: one public, one confidential authored by recruiter_1
    note_public = CandidateInternalNote(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        author_id=s["recruiter_1"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        content="General background looks solid.",
        category="general",
        is_confidential=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    note_confidential = CandidateInternalNote(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        author_id=s["recruiter_1"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        content="Compensation expectation is above budget band.",
        category="compensation",
        is_confidential=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    mock_notes_res = MagicMock()
    mock_notes_res.scalars.return_value.all.return_value = [note_public, note_confidential]

    db.execute.side_effect = [mock_auth_res, mock_notes_res]

    # Recruiter 2 (not author, not admin) views notes
    notes_rec2 = await service.get_internal_notes(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        actor_id=s["recruiter_2"].id,
        is_admin=False,
    )
    # Recruiter 2 should only see the public note!
    assert len(notes_rec2) == 1
    assert notes_rec2[0].content == "General background looks solid."

    # Author (Alice Recruiter) views notes
    db.execute.side_effect = [mock_auth_res, mock_notes_res]
    notes_author = await service.get_internal_notes(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        actor_id=s["recruiter_1"].id,
        is_admin=False,
    )
    # Author sees both notes!
    assert len(notes_author) == 2


@pytest.mark.asyncio
async def test_update_internal_note_author_and_admin_permitted_others_forbidden(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    note = CandidateInternalNote(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        author_id=s["recruiter_1"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        content="Initial notes",
        category="general",
        is_confidential=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.get.return_value = note

    req = UpdateInternalNoteRequest(content="Updated note content with more details")

    # 1. Recruiter 2 attempts to edit Alice's note -> FORBIDDEN
    with pytest.raises(AuthorizationException) as exc:
        await service.update_internal_note(
            db=db,
            tenant_id=s["tenant_a_id"],
            note_id=note.id,
            actor_id=s["recruiter_2"].id,
            is_admin=False,
            request=req,
        )
    assert exc.value.code == "NOTE_EDIT_FORBIDDEN"

    # 2. Author Alice edits her note -> SUCCEEDS
    resp = await service.update_internal_note(
        db=db,
        tenant_id=s["tenant_a_id"],
        note_id=note.id,
        actor_id=s["recruiter_1"].id,
        is_admin=False,
        request=req,
    )
    assert resp.content == "Updated note content with more details"

    # 3. Org Admin edits note -> SUCCEEDS
    admin_req = UpdateInternalNoteRequest(content="Admin override note")
    resp_admin = await service.update_internal_note(
        db=db,
        tenant_id=s["tenant_a_id"],
        note_id=note.id,
        actor_id=s["admin_user"].id,
        is_admin=True,
        request=admin_req,
    )
    assert resp_admin.content == "Admin override note"


@pytest.mark.asyncio
async def test_submit_and_get_review_feedback_scorecards(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()
    db.get.return_value = s["app_1"]

    # No existing feedback
    mock_existing = MagicMock()
    mock_existing.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_existing

    added_objects = []
    db.add = MagicMock(side_effect=lambda o: added_objects.append(o))

    req = SubmitReviewFeedbackRequest(
        recommendation="strong_yes",
        technical_rating=5,
        communication_rating=4,
        cultural_rating=5,
        overall_rating=5,
        summary="Exceptional systems architect with proven leadership in cloud migration.",
        pros=["Deep Kubernetes expertise", "Clear communicator"],
        cons=["Requires remote setup"],
    )

    resp = await service.submit_review_feedback(
        db=db,
        tenant_id=s["tenant_a_id"],
        application_id=s["app_1"].id,
        reviewer_id=s["hm_user"].id,
        reviewer_name="Carol Manager",
        reviewer_role="hiring_manager",
        request=req,
    )

    assert resp.application_id == s["app_1"].id
    assert resp.reviewer_name == "Carol Manager"
    assert resp.recommendation == "strong_yes"
    assert resp.overall_rating == 5
    assert len(added_objects) == 1
    assert isinstance(added_objects[0], CandidateReviewFeedback)


@pytest.mark.asyncio
async def test_create_and_complete_recruitment_task(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    # Candidate belongs to tenant
    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = s["app_1"].id

    # Assignee lookup in OrganizationMembership
    mock_assignee = MagicMock()
    mock_assignee.scalar_one_or_none.return_value = s["recruiter_2"]

    db.execute.side_effect = [mock_auth, mock_assignee]

    added_objects = []
    db.add = MagicMock(side_effect=lambda o: added_objects.append(o))

    # 1. Create task
    req = CreateRecruitmentTaskRequest(
        application_id=s["app_1"].id,
        title="Schedule Technical Interview Round 1",
        description="Align with Carol Manager for 60 min system design slot",
        task_type="schedule_interview",
        assignee_id=s["recruiter_2"].id,
    )

    task_resp = await service.create_task(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        creator_id=s["recruiter_1"].id,
        creator_name="Alice Recruiter",
        request=req,
    )

    assert task_resp.title == "Schedule Technical Interview Round 1"
    assert task_resp.assignee_name == "Bob Recruiter"
    assert task_resp.is_completed is False

    # 2. Complete task
    created_task = added_objects[0]
    db.get.return_value = created_task

    comp_req = UpdateRecruitmentTaskRequest(is_completed=True)
    comp_resp = await service.update_task(
        db=db,
        tenant_id=s["tenant_a_id"],
        task_id=created_task.id,
        actor_id=s["recruiter_2"].id,
        request=comp_req,
    )

    assert comp_resp.is_completed is True
    assert comp_resp.completed_at is not None


@pytest.mark.asyncio
async def test_task_assignee_must_be_organization_member(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = s["app_1"].id

    # Assignee not found in org
    mock_assignee = MagicMock()
    mock_assignee.scalar_one_or_none.return_value = None

    db.execute.side_effect = [mock_auth, mock_assignee]

    req = CreateRecruitmentTaskRequest(
        title="Reference Check",
        task_type="reference_check",
        assignee_id=s["external_user"].id,
    )

    with pytest.raises(ValidationException) as exc:
        await service.create_task(
            db=db,
            tenant_id=s["tenant_a_id"],
            candidate_id=s["candidate_user"].id,
            creator_id=s["recruiter_1"].id,
            creator_name="Alice Recruiter",
            request=req,
        )

    assert exc.value.code == "USER_NOT_ORGANIZATION_MEMBER"


@pytest.mark.asyncio
async def test_get_candidate_timeline_separates_internal_from_candidate_events(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    # 1. Candidate check
    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = s["app_1"].id

    # 2. Apps
    mock_apps = MagicMock()
    mock_apps.all.return_value = [(s["app_1"], s["job_1"])]

    # 3. Stage history
    stage_hist = ApplicationStageHistory(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        application_id=s["app_1"].id,
        previous_stage="applied",
        new_stage="screening",
        actor_id=s["recruiter_1"].id,
        actor_role="recruiter",
        reason="Passed initial resume review",
        created_at=utc_now(),
    )
    stage_hist.actor = s["recruiter_1"]
    mock_sh = MagicMock()
    mock_sh.scalars.return_value.all.return_value = [stage_hist]

    # 4. Notes
    note = CandidateInternalNote(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        author_name="Alice Recruiter",
        author_role="recruiter",
        content="Confidential salary note",
        category="compensation",
        is_confidential=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    mock_notes = MagicMock()
    mock_notes.scalars.return_value.all.return_value = [note]

    # 5. Reviews
    review = CandidateReviewFeedback(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        application_id=s["app_1"].id,
        reviewer_id=s["hm_user"].id,
        reviewer_name="Carol Manager",
        reviewer_role="hiring_manager",
        recommendation="yes",
        summary="Good communication",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    mock_revs = MagicMock()
    mock_revs.scalars.return_value.all.return_value = [review]

    # 6. Tasks
    task = CandidateRecruitmentTask(
        id=generate_uuid7(),
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        creator_name="Alice Recruiter",
        title="Check references",
        task_type="reference_check",
        is_completed=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    mock_tasks = MagicMock()
    mock_tasks.scalars.return_value.all.return_value = [task]

    # 7. Job assignments
    mock_ja = MagicMock()
    mock_ja.scalars.return_value.all.return_value = []

    db.execute.side_effect = [
        mock_auth,
        mock_apps,
        mock_sh,
        mock_notes,
        mock_revs,
        mock_tasks,
        mock_ja,
    ]

    # Internal HR viewer sees all internal and candidate events
    timeline = await service.get_candidate_timeline(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        is_internal_viewer=True,
    )

    internal_events = [e for e in timeline.events if e.is_internal]
    candidate_events = [e for e in timeline.events if not e.is_internal]

    assert len(internal_events) >= 3  # note, review, task
    assert len(candidate_events) >= 2  # application submitted, stage advanced


@pytest.mark.asyncio
async def test_candidate_timeline_hides_internal_events_for_candidate_viewer(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = s["app_1"].id

    mock_apps = MagicMock()
    mock_apps.all.return_value = [(s["app_1"], s["job_1"])]

    mock_sh = MagicMock()
    mock_sh.scalars.return_value.all.return_value = []

    db.execute.side_effect = [mock_auth, mock_apps, mock_sh]

    # Candidate viewer: is_internal_viewer = False
    timeline = await service.get_candidate_timeline(
        db=db,
        tenant_id=s["tenant_a_id"],
        candidate_id=s["candidate_user"].id,
        is_internal_viewer=False,
    )

    # Must contain zero internal events
    for event in timeline.events:
        assert event.is_internal is False


@pytest.mark.asyncio
async def test_cross_tenant_candidate_review_isolation(review_setup):
    service = HrReviewService()
    s = review_setup
    db = AsyncMock()

    # Candidate has no application in Tenant B
    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_auth

    req = CreateInternalNoteRequest(content="Attempting unauthorized note across tenants")

    with pytest.raises(AuthorizationException) as exc:
        await service.add_internal_note(
            db=db,
            tenant_id=s["tenant_b_id"],
            candidate_id=s["candidate_user"].id,
            author_id=s["recruiter_1"].id,
            author_name="Alice Recruiter",
            author_role="recruiter",
            request=req,
        )

    assert exc.value.code == "CANDIDATE_ACCESS_FORBIDDEN"
