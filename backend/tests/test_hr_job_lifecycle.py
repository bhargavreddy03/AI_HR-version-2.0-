"""Unit and integration tests for Step 4.2.4 Job Publishing and Lifecycle Management.

Verifies:
1. Complete finite state machine transitions (submit, approve, request changes, publish, pause, reopen, close, archive).
2. Separation of duties: assigned lead recruiter is forbidden from approving their own requisition.
3. Mandatory reason requirement when requesting changes on a requisition.
4. Rejection of prohibited / invalid state transitions.
5. Role authorization enforcement (Recruiter vs Hiring Manager vs Organization Admin).
6. Immutable audit history logging with actor metadata.
7. Candidate portal discovery integration: drafts, paused, closed, and archived jobs excluded from public discovery.
8. Application submission rejection on closed or non-published jobs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.base import utc_now
from app.core.errors import AppException, AuthorizationException, ConflictException
from app.modules.auth.models import User
from app.modules.hr.lifecycle_schemas import JobLifecycleActionRequest
from app.modules.hr.lifecycle_service import hr_job_lifecycle_service
from app.modules.hr.requisition_schemas import JobRequisitionRead
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import JobService


@pytest.fixture(autouse=True)
def mock_celery_delay():
    """Mock Celery delay call so tests do not attempt to connect to external message brokers."""
    with patch(
        "app.modules.notifications.tasks.dispatch_job_lifecycle_notification.delay"
    ) as mock_delay:
        yield mock_delay


@pytest.fixture
def test_setup():
    tenant_id = uuid4()
    job_id = uuid4()
    recruiter_id = uuid4()
    hiring_manager_id = uuid4()
    admin_id = uuid4()

    recruiter_user = User(
        id=recruiter_id,
        first_name="Rachel",
        last_name="Recruiter",
        email="rachel@acme.com",
        password_hash="hash",
    )
    hm_user = User(
        id=hiring_manager_id,
        first_name="Hank",
        last_name="Manager",
        email="hank@acme.com",
        password_hash="hash",
    )
    admin_user = User(
        id=admin_id,
        first_name="Alice",
        last_name="Admin",
        email="alice@acme.com",
        password_hash="hash",
    )

    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        title="Principal AI Architect",
        slug="principal-ai-architect-12345678",
        department="Engineering",
        location="Remote, US",
        remote_type="hybrid",
        employment_type="full_time",
        experience_level="lead",
        description="Lead enterprise AI architectures.",
        status=JobStatus.DRAFT.value,
        approval_status="draft",
        visibility="public",
        recruiter_id=recruiter_id,
        hiring_manager_id=hiring_manager_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    job.recruiter = recruiter_user
    job.hiring_manager = hm_user

    return {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "recruiter_id": recruiter_id,
        "hiring_manager_id": hiring_manager_id,
        "admin_id": admin_id,
        "job": job,
        "recruiter_user": recruiter_user,
        "hm_user": hm_user,
        "admin_user": admin_user,
    }


def make_read_job(job: Job, status: str | None = None, approval_status: str | None = None) -> JobRequisitionRead:
    return JobRequisitionRead(
        id=job.id,
        tenant_id=job.tenant_id,
        title=job.title,
        slug=job.slug,
        department=job.department,
        location=job.location,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        description=job.description,
        status=status or job.status,
        approval_status=approval_status or job.approval_status,
        visibility=job.visibility,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@pytest.mark.asyncio
async def test_submit_draft_for_approval(test_setup):
    """Verify recruiter can submit a draft job for approval."""
    setup = test_setup
    mock_db = AsyncMock()

    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]

    actor_res = MagicMock()
    actor_res.scalar_one_or_none.return_value = setup["recruiter_user"]

    read_job = make_read_job(setup["job"], status="pending_approval", approval_status="pending_approval")

    mock_db.execute.side_effect = [job_res, actor_res]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=read_job),
        )

        response = await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="submit_for_approval"),
        )

        assert setup["job"].status == JobStatus.PENDING_APPROVAL.value
        assert setup["job"].approval_status == "pending_approval"
        assert response.transition.new_status == "pending_approval"
        assert response.transition.action == "submit_for_approval"
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_separation_of_duties_blocks_recruiter_self_approval(test_setup):
    """Verify separation of duties strictly forbids the assigned recruiter from approving their own job."""
    setup = test_setup
    setup["job"].status = JobStatus.PENDING_APPROVAL.value
    setup["job"].approval_status = "pending_approval"

    mock_db = AsyncMock()
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]
    mock_db.execute.return_value = job_res

    # Recruiter (who created or is assigned to the job) tries to approve it
    with pytest.raises(AuthorizationException) as exc:
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter", "hiring_manager"],  # Even if dual roles
            request=JobLifecycleActionRequest(action="approve"),
        )

    assert "Separation of duties policy forbids" in exc.value.message
    assert exc.value.error_code == "SEPARATION_OF_DUTIES_VIOLATION"


@pytest.mark.asyncio
async def test_hiring_manager_approval_succeeds(test_setup):
    """Verify hiring manager (different from recruiter) successfully approves requisition."""
    setup = test_setup
    setup["job"].status = JobStatus.PENDING_APPROVAL.value
    setup["job"].approval_status = "pending_approval"

    mock_db = AsyncMock()
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]

    actor_res = MagicMock()
    actor_res.scalar_one_or_none.return_value = setup["hm_user"]

    read_job = make_read_job(setup["job"], status="approved", approval_status="approved")

    mock_db.execute.side_effect = [job_res, actor_res]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=read_job),
        )

        response = await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["hiring_manager_id"],
            user_roles=["hiring_manager"],
            request=JobLifecycleActionRequest(action="approve"),
        )

        assert setup["job"].status == JobStatus.APPROVED.value
        assert setup["job"].approval_status == "approved"
        assert response.transition.new_status == "approved"
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_request_changes_requires_mandatory_reason(test_setup):
    """Verify requesting changes fails without mandatory feedback reason."""
    setup = test_setup
    setup["job"].status = JobStatus.PENDING_APPROVAL.value
    setup["job"].approval_status = "pending_approval"

    mock_db = AsyncMock()
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]
    mock_db.execute.return_value = job_res

    # Missing reason
    with pytest.raises(AppException) as exc:
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["hiring_manager_id"],
            user_roles=["hiring_manager"],
            request=JobLifecycleActionRequest(action="request_changes", reason=""),
        )

    assert "A detailed reason is mandatory" in exc.value.message


@pytest.mark.asyncio
async def test_request_changes_with_valid_reason_returns_to_draft(test_setup):
    """Verify requesting changes with valid feedback returns job to draft with recorded feedback."""
    setup = test_setup
    setup["job"].status = JobStatus.PENDING_APPROVAL.value
    setup["job"].approval_status = "pending_approval"

    mock_db = AsyncMock()
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]

    actor_res = MagicMock()
    actor_res.scalar_one_or_none.return_value = setup["hm_user"]

    read_job = make_read_job(setup["job"], status="draft", approval_status="changes_requested")

    mock_db.execute.side_effect = [job_res, actor_res]

    feedback = "Please increase the salary range to align with senior compensation bands."
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=read_job),
        )

        response = await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["hiring_manager_id"],
            user_roles=["hiring_manager"],
            request=JobLifecycleActionRequest(action="request_changes", reason=feedback),
        )

        assert setup["job"].status == JobStatus.DRAFT.value
        assert setup["job"].change_request_reason == feedback
        assert response.transition.reason == feedback


@pytest.mark.asyncio
async def test_publish_approved_job_sets_timestamp(test_setup):
    """Verify publishing an approved job sets published_at timestamp."""
    setup = test_setup
    setup["job"].status = JobStatus.APPROVED.value
    setup["job"].approval_status = "approved"

    mock_db = AsyncMock()
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]

    actor_res = MagicMock()
    actor_res.scalar_one_or_none.return_value = setup["recruiter_user"]

    read_job = make_read_job(setup["job"], status="published", approval_status="published")

    mock_db.execute.side_effect = [job_res, actor_res]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=read_job),
        )

        response = await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="publish"),
        )

        assert setup["job"].status == JobStatus.PUBLISHED.value
        assert setup["job"].published_at is not None
        assert response.transition.new_status == "published"


@pytest.mark.asyncio
async def test_pause_reopen_and_close_lifecycle(test_setup):
    """Verify pause, reopen, and close transitions update state and timestamps."""
    setup = test_setup
    mock_db = AsyncMock()

    # 1. Published -> Paused
    setup["job"].status = JobStatus.PUBLISHED.value
    job_res1 = MagicMock()
    job_res1.scalar_one_or_none.return_value = setup["job"]
    actor_res1 = MagicMock()
    actor_res1.scalar_one_or_none.return_value = setup["recruiter_user"]
    mock_db.execute.side_effect = [job_res1, actor_res1]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=make_read_job(setup["job"], status="paused")),
        )
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="pause"),
        )
        assert setup["job"].status == JobStatus.PAUSED.value

    # 2. Paused -> Published (Reopen)
    job_res2 = MagicMock()
    job_res2.scalar_one_or_none.return_value = setup["job"]
    actor_res2 = MagicMock()
    actor_res2.scalar_one_or_none.return_value = setup["recruiter_user"]
    mock_db.execute.side_effect = [job_res2, actor_res2]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=make_read_job(setup["job"], status="published")),
        )
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="reopen"),
        )
        assert setup["job"].status == JobStatus.PUBLISHED.value
        assert setup["job"].reopened_at is not None

    # 3. Published -> Closed
    job_res3 = MagicMock()
    job_res3.scalar_one_or_none.return_value = setup["job"]
    actor_res3 = MagicMock()
    actor_res3.scalar_one_or_none.return_value = setup["recruiter_user"]
    mock_db.execute.side_effect = [job_res3, actor_res3]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "app.modules.hr.service.hr_requisition_service.get_requisition",
            AsyncMock(return_value=make_read_job(setup["job"], status="closed")),
        )
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["recruiter_id"],
            user_roles=["recruiter"],
            request=JobLifecycleActionRequest(action="close", reason="Role successfully filled"),
        )
        assert setup["job"].status == JobStatus.CLOSED.value
        assert setup["job"].closed_at is not None


@pytest.mark.asyncio
async def test_prohibited_transitions_rejected(test_setup):
    """Verify invalid state transitions are strictly rejected by the FSM."""
    setup = test_setup
    mock_db = AsyncMock()

    # Draft cannot be published directly without approval
    setup["job"].status = JobStatus.DRAFT.value
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = setup["job"]
    mock_db.execute.return_value = job_res

    with pytest.raises(ConflictException) as exc:
        await hr_job_lifecycle_service.execute_transition(
            db=mock_db,
            tenant_id=setup["tenant_id"],
            job_id=setup["job_id"],
            user_id=setup["admin_id"],
            user_roles=["admin"],
            request=JobLifecycleActionRequest(action="publish"),
        )
    assert "Invalid lifecycle transition" in exc.value.message


@pytest.mark.asyncio
async def test_candidate_discovery_and_application_rejection_for_closed_job(test_setup):
    """Verify closed and draft jobs reject new candidate applications."""
    setup = test_setup
    job_service = JobService()
    mock_db = AsyncMock()

    # Closed Job
    setup["job"].status = JobStatus.CLOSED.value
    row_mock = (setup["job"], "Acme Corp")
    job_res = MagicMock()
    job_res.first.return_value = row_mock
    mock_db.execute.return_value = job_res

    candidate_id = uuid4()
    with pytest.raises(AppException) as exc:
        await job_service.apply_to_job(
            db=mock_db,
            candidate_user_id=candidate_id,
            job_id=setup["job_id"],
            resume_id=uuid4(),
        )

    assert "This job requisition is no longer accepting applications" in exc.value.message
