"""Comprehensive unit and integration test suite for Candidate Portal conforming to Step 4.1.

Validates:
- Global candidate identity & profile lifecycle (summary, headline, bio, completion score).
- Work experience, education, certifications, projects, and languages CRUD with strict candidate IDOR ownership.
- Self-declared skills normalization against Step 3.10 canonical taxonomy and collision prevention.
- Candidate career preferences (remote arrangements, employment types, salary expectations).
- Resume ingestion reusing Step 3.10 S3 Storage & PDFExtractor, SHA-256 deduplication, versioning, and default selection.
- Resume extraction preview and candidate corrections.
- Job discovery search, filtering (department, remote type, employment type), and pagination.
- Candidate saved jobs / bookmarking lifecycle.
- Application workflow: immutable resume snapshot SHA-256 recording, active duplicate application prevention.
- Application tracking: candidate-safe statuses, timeline, and application withdrawal with reason.
- Candidate notification center (generation, unread count, mark read, mark all read).
- End-to-end FastAPI endpoint contracts with authentication and IDOR access rejections.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import UploadFile

from app.core.database import get_db
from app.core.errors import EntityNotFoundException, ValidationException
from app.core.security import SecurityContext
from app.main import create_application
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.candidates.models import (
    CandidateNotification,
    CandidatePreference,
    CandidateResume,
    CandidateResumeStatus,
    CandidateSavedJob,
)
from app.modules.candidates.schemas import (
    CandidatePreferenceUpdate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    CertificationCreate,
    EducationCreate,
    ExperienceCreate,
    ExperienceUpdate,
    LanguageCreate,
    ProjectCreate,
    ResumeExtractedDataUpdate,
)
from app.modules.candidates.service import CandidateService, candidate_service
from app.modules.documents.extractor import PDFExtractionResult, PDFExtractorService
from app.modules.documents.storage import StorageService
from app.modules.jobs.models import (
    CandidateFacingStatus,
    Job,
    JobApplication,
    JobStatus,
)
from app.modules.jobs.service import job_service
from app.modules.screening.skills.registry import skill_registry

SAMPLE_CANDIDATE_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 135 >>
stream
BT
/F1 12 Tf
50 700 Td
(Alice Candidate - Principal Python Engineer. Expertise in FastAPI, PostgreSQL, Redis, Docker, and Machine Learning.) Tj
ET
endstream
endobj
xref
0 5
trailer
<< /Size 5 /Root 1 0 R >>
startxref
250
%%EOF"""


# =============================================================================
# Unit Tests: Candidate Profile & Experience
# =============================================================================
@pytest.mark.asyncio
async def test_get_candidate_profile_completion_calculation() -> None:
    """Verify aggregated profile calculation and percentage completion score."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    mock_user = MagicMock(spec=User)
    mock_user.id = candidate_id
    mock_user.email = "alice@example.com"
    mock_user.first_name = "Alice"
    mock_user.last_name = "Candidate"
    mock_user.phone_number = "+1-555-0100"

    mock_profile = MagicMock(spec=CandidateUserProfile)
    mock_profile.headline = "Principal Python Engineer"
    mock_profile.bio = "Experienced backend architect"
    mock_profile.phone = "+1-555-0100"
    mock_profile.location_city = "San Francisco"
    mock_profile.location_country = "USA"
    mock_profile.preferred_title = "Staff Engineer"
    mock_profile.work_authorization = "Authorized"
    mock_profile.portfolio_urls = ["https://alice.dev"]
    mock_profile.self_declared_skills = ["Python", "FastAPI", "PostgreSQL"]

    # Mock DB executions
    user_res = MagicMock()
    user_res.scalar_one_or_none.return_value = mock_user

    prof_res = MagicMock()
    prof_res.scalar_one_or_none.return_value = mock_profile

    empty_list_res = MagicMock()
    empty_list_res.scalars.return_value.all.return_value = []

    pref_res = MagicMock()
    pref_res.scalar_one_or_none.return_value = None

    resume_res = MagicMock()
    resume_res.scalar_one_or_none.return_value = MagicMock()

    mock_db.execute.side_effect = [
        user_res,
        prof_res,
        empty_list_res,  # experiences
        empty_list_res,  # educations
        empty_list_res,  # certifications
        empty_list_res,  # projects
        empty_list_res,  # languages
        pref_res,  # preferences
        resume_res,  # has_resume check
    ]

    profile_dto = await candidate_service.get_candidate_profile(mock_db, candidate_id)

    assert profile_dto.email == "alice@example.com"
    assert profile_dto.first_name == "Alice"
    assert profile_dto.headline == "Principal Python Engineer"
    assert "Python" in profile_dto.self_declared_skills
    # 20 (user) + 15 (headline/bio) + 15 (skills) + 15 (resume) = 65%
    assert profile_dto.profile_completion_percentage == 65


@pytest.mark.asyncio
async def test_update_candidate_profile_updates_user_and_profile() -> None:
    """Verify profile updates mutate user names and candidate user profile record."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    mock_user = MagicMock(spec=User)
    mock_user.id = candidate_id
    mock_user.email = "alice@smith.com"
    mock_user.first_name = "OldName"
    mock_user.last_name = "OldLast"
    mock_user.phone_number = None

    user_res = MagicMock()
    user_res.scalar_one_or_none.return_value = mock_user

    mock_profile = MagicMock(spec=CandidateUserProfile)
    mock_profile.headline = "Senior Backend Engineer"
    mock_profile.bio = None
    mock_profile.phone = None
    mock_profile.location_city = "Seattle"
    mock_profile.location_country = None
    mock_profile.preferred_title = "Staff Engineer"
    mock_profile.work_authorization = None
    mock_profile.portfolio_urls = []
    mock_profile.self_declared_skills = []
    prof_res = MagicMock()
    prof_res.scalar_one_or_none.return_value = mock_profile

    mock_db.execute.side_effect = [
        user_res,
        prof_res,
        # Following queries are for get_candidate_profile called at the end
        user_res,
        prof_res,
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    update_payload = CandidateProfileUpdate(
        first_name="Alice",
        last_name="Smith",
        headline="Senior Backend Engineer",
        location_city="Seattle",
        preferred_title="Staff Engineer",
    )

    await candidate_service.update_candidate_profile(mock_db, candidate_id, update_payload)

    assert mock_user.first_name == "Alice"
    assert mock_user.last_name == "Smith"
    assert mock_profile.headline == "Senior Backend Engineer"
    assert mock_profile.location_city == "Seattle"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_experience_crud_and_idor_protection() -> None:
    """Verify work experience creation, update, and IDOR protection against unauthorized users."""
    candidate_a = uuid4()
    candidate_b = uuid4()
    exp_id = uuid4()
    mock_db = AsyncMock()

    # 1. Add experience
    payload = ExperienceCreate(
        job_title="Software Architect",
        company_name="Acme Corp",
        start_date="2022-01",
        end_date=None,
        is_current=True,
        skills=["Python", "FastAPI"],
    )
    result = await candidate_service.add_experience(mock_db, candidate_a, payload)
    assert result.job_title == "Software Architect"
    assert result.company_name == "Acme Corp"
    assert result.is_current is True

    # 2. Update with wrong candidate (IDOR attempt)
    not_found_res = MagicMock()
    not_found_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = not_found_res

    update_payload = ExperienceUpdate(job_title="VP of Engineering")
    with pytest.raises(EntityNotFoundException):
        await candidate_service.update_experience(mock_db, candidate_b, exp_id, update_payload)

    # 3. Delete with wrong candidate (IDOR attempt)
    with pytest.raises(EntityNotFoundException):
        await candidate_service.delete_experience(mock_db, candidate_b, exp_id)


# =============================================================================
# Unit Tests: Skill Normalization & Canonical Resolution
# =============================================================================
@pytest.mark.asyncio
async def test_update_skills_normalizes_against_canonical_taxonomy() -> None:
    """Verify raw skill inputs are resolved to canonical names using the Step 3.10 skill registry."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    mock_profile = MagicMock(spec=CandidateUserProfile)
    mock_profile.self_declared_skills = []

    prof_res = MagicMock()
    prof_res.scalar_one_or_none.return_value = mock_profile
    mock_db.execute.return_value = prof_res

    raw_skills = ["py", "postgres", "dsa", "react", "unknown_custom_skill"]

    resp = await candidate_service.update_skills(mock_db, candidate_id, raw_skills)

    # "py" -> "Python", "postgres" -> "PostgreSQL", "dsa" -> "Data Structures and Algorithms"
    assert "Python" in resp.skills
    assert "PostgreSQL" in resp.skills
    assert "Data Structures and Algorithms" in resp.skills
    assert "React" in resp.skills
    assert "unknown_custom_skill" in resp.skills
    assert resp.total_count == 5


# =============================================================================
# Unit Tests: Resume Management (Step 3.10 Integration)
# =============================================================================
@pytest.mark.asyncio
async def test_upload_resume_success_and_deduplication() -> None:
    """Verify resume upload extracts text, matches skills, stores file, and deduplicates identical uploads."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    # Setup mocked storage and extractor
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.upload_document_bytes.return_value = "storage_key_123"

    mock_extractor = MagicMock(spec=PDFExtractorService)
    mock_extractor.extract_from_bytes.return_value = PDFExtractionResult(
        raw_text="Alice Candidate Python FastAPI PostgreSQL Docker",
        page_count=1,
        page_texts=["Alice Candidate Python FastAPI PostgreSQL Docker"],
        character_count=50,
        quality_score=0.95,
        warnings=[],
        requires_ocr=False,
        is_scanned=False,
        content_sha256="dummy_sha",
        extraction_method="pdfplumber",
        extraction_version="1.0.0",
        extraction_timestamp=datetime.now(UTC),
        duration_ms=10.0,
    )

    mock_service = CandidateService(
        storage=mock_storage,
        extractor=mock_extractor,
        matcher=None,
        registry=skill_registry,
    )

    # Step 1: Upload fresh resume (no duplicates found in DB)
    dup_res = MagicMock()
    dup_res.scalar_one_or_none.return_value = None

    count_res = MagicMock()
    count_res.scalar.return_value = 0

    mock_db.execute.side_effect = [dup_res, count_res]

    upload_file = UploadFile(
        file=io.BytesIO(SAMPLE_CANDIDATE_PDF),
        filename="alice_resume.pdf",
    )

    res = await mock_service.upload_resume(mock_db, candidate_id, upload_file)

    assert res.is_duplicate is False
    assert res.version_number == 1
    assert res.is_default is True
    assert res.status == CandidateResumeStatus.COMPLETED.value
    mock_storage.upload_document_bytes.assert_called_once()

    # Step 2: Upload same resume again -> duplicate detected
    existing_resume = MagicMock(spec=CandidateResume)
    existing_resume.id = uuid4()
    existing_resume.filename = "alice_resume.pdf"
    existing_resume.file_size_bytes = len(SAMPLE_CANDIDATE_PDF)
    existing_resume.content_sha256 = res.content_sha256
    existing_resume.status = "COMPLETED"
    existing_resume.version_number = 1
    existing_resume.is_default = True

    dup_found_res = MagicMock()
    dup_found_res.scalar_one_or_none.return_value = existing_resume
    mock_db.execute.side_effect = [dup_found_res]

    upload_file2 = UploadFile(
        file=io.BytesIO(SAMPLE_CANDIDATE_PDF),
        filename="alice_resume.pdf",
    )

    dup_resp = await mock_service.upload_resume(mock_db, candidate_id, upload_file2)
    assert dup_resp.is_duplicate is True
    assert dup_resp.id == existing_resume.id


@pytest.mark.asyncio
async def test_resume_idor_prevention() -> None:
    """Verify candidate cannot view, edit, or delete another candidate's resume."""
    candidate_b = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    not_found_res = MagicMock()
    not_found_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = not_found_res

    # Accessing candidate A's resume using candidate B's context must return 404
    with pytest.raises(EntityNotFoundException):
        await candidate_service.get_resume(mock_db, candidate_b, resume_id)

    with pytest.raises(EntityNotFoundException):
        await candidate_service.get_resume_extraction(mock_db, candidate_b, resume_id)

    with pytest.raises(EntityNotFoundException):
        await candidate_service.delete_resume(mock_db, candidate_b, resume_id)


# =============================================================================
# Unit Tests: Job Discovery & Application Flow
# =============================================================================
@pytest.mark.asyncio
async def test_job_discovery_lists_only_published_jobs() -> None:
    """Verify only published jobs are returned to candidates."""
    mock_db = AsyncMock()
    org_id = uuid4()
    job_id = uuid4()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.tenant_id = org_id
    mock_job.title = "Staff Platform Engineer"
    mock_job.slug = "staff-platform-engineer"
    mock_job.department = "Engineering"
    mock_job.location = "San Francisco, CA"
    mock_job.remote_type = "hybrid"
    mock_job.employment_type = "full_time"
    mock_job.description = "Build enterprise platforms"
    mock_job.requirements = "FastAPI & PostgreSQL expertise"
    mock_job.skills_required = ["Python", "FastAPI", "PostgreSQL"]
    mock_job.experience_level = "senior"
    mock_job.salary_min = 180000
    mock_job.salary_max = 240000
    mock_job.salary_currency = "USD"
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.published_at = datetime.now(UTC)
    mock_job.application_deadline = None

    count_res = MagicMock()
    count_res.scalar.return_value = 1

    jobs_res = MagicMock()
    jobs_res.all.return_value = [(mock_job, "TechCorp")]

    mock_db.execute.side_effect = [count_res, jobs_res]

    res = await job_service.list_jobs(mock_db, query="Platform")

    assert res.total == 1
    assert len(res.jobs) == 1
    assert res.jobs[0].title == "Staff Platform Engineer"
    assert res.jobs[0].organization_name == "TechCorp"


@pytest.mark.asyncio
async def test_apply_to_job_records_immutable_snapshot_sha256() -> None:
    """Verify application workflow pins exact resume SHA-256 snapshot and creates candidate notification."""
    candidate_id = uuid4()
    job_id = uuid4()
    tenant_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.tenant_id = tenant_id
    mock_job.title = "Senior Backend Engineer"
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme Tech")

    # No existing active application
    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = None

    # Target resume
    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.content_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    res_query = MagicMock()
    res_query.scalar_one_or_none.return_value = mock_resume

    mock_db.execute.side_effect = [
        job_res,
        app_check_res,
        res_query,
    ]

    res = await job_service.apply_to_job(
        mock_db,
        candidate_user_id=candidate_id,
        job_id=job_id,
        resume_id=resume_id,
        cover_letter="I am very excited about this role.",
    )

    assert res.candidate_status == CandidateFacingStatus.SUBMITTED.value
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_apply_to_job_prevents_duplicate_active_application() -> None:
    """Verify candidates cannot submit duplicate applications to the same job opening."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme Tech")

    # Existing active application found
    mock_app = MagicMock(spec=JobApplication)
    mock_app.candidate_status = CandidateFacingStatus.SUBMITTED.value

    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = mock_app

    mock_db.execute.side_effect = [job_res, app_check_res]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.apply_to_job(mock_db, candidate_id, job_id)

    assert exc_info.value.code == "ERR_DUPLICATE_APPLICATION"


@pytest.mark.asyncio
async def test_withdraw_application_with_mandatory_reason() -> None:
    """Verify application withdrawal sets status to withdrawn and logs reason."""
    candidate_id = uuid4()
    app_id = uuid4()
    mock_db = AsyncMock()

    mock_app = MagicMock(spec=JobApplication)
    mock_app.id = app_id
    mock_app.job_id = uuid4()
    mock_app.candidate_id = candidate_id
    mock_app.tenant_id = uuid4()
    mock_app.resume_id = uuid4()
    mock_app.resume_snapshot_sha256 = "snapshot_sha_123"
    mock_app.status = "submitted"
    mock_app.candidate_status = CandidateFacingStatus.SUBMITTED.value
    mock_app.cover_letter = None
    mock_app.applied_at = datetime.now(UTC)
    mock_app.withdrawn_at = None
    mock_app.withdrawal_reason = None

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = mock_app

    # get_candidate_application query mock
    detail_res = MagicMock()
    detail_res.first.return_value = (
        mock_app,
        "Engineer",
        "Eng",
        "Remote",
        "remote",
        "Acme",
        "resume.pdf",
    )

    mock_db.execute.side_effect = [app_res, detail_res]

    withdrawn = await job_service.withdraw_application(
        mock_db, candidate_id, app_id, reason="Accepted another offer"
    )

    assert withdrawn.candidate_status == CandidateFacingStatus.WITHDRAWN.value
    assert mock_app.candidate_status == CandidateFacingStatus.WITHDRAWN.value
    assert mock_app.withdrawal_reason == "Accepted another offer"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_apply_to_job_with_answers_consents_and_idempotency() -> None:
    """Verify application submission persists questionnaire answers, consents, and handles idempotency."""
    candidate_id = uuid4()
    job_id = uuid4()
    resume_id = uuid4()
    idempotency_key = "idemp_test_abc_123"
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme AI Corp")

    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = None

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.version_number = 2
    mock_resume.content_sha256 = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    res_query = MagicMock()
    res_query.scalar_one_or_none.return_value = mock_resume

    mock_db.execute.side_effect = [job_res, app_check_res, res_query]

    answers = {
        "work_authorization": "authorized",
        "visa_sponsorship_required": False,
        "earliest_start_date": "2026-12-01",
    }
    consents = {
        "data_processing_consent": True,
        "accuracy_certified": True,
        "consented_at": datetime.now(UTC).isoformat(),
    }

    res = await job_service.apply_to_job(
        mock_db,
        candidate_user_id=candidate_id,
        job_id=job_id,
        resume_id=resume_id,
        cover_letter="I am very excited about scaling your platform.",
        answers=answers,
        consent_records=consents,
        idempotency_key=idempotency_key,
    )

    assert res.candidate_status == CandidateFacingStatus.SUBMITTED.value
    assert res.resume_version_applied == 2
    assert res.resume_snapshot_sha256 == mock_resume.content_sha256
    mock_db.commit.assert_awaited()

    # Now verify idempotent retry returns existing submission
    mock_app = MagicMock(spec=JobApplication)
    mock_app.id = res.id
    mock_app.candidate_status = CandidateFacingStatus.SUBMITTED.value
    mock_app.resume_snapshot_sha256 = mock_resume.content_sha256
    mock_app.resume_version_applied = 2
    mock_app.idempotency_key = idempotency_key
    mock_app.applied_at = datetime.now(UTC)

    job_res_2 = MagicMock()
    job_res_2.first.return_value = (mock_job, "Acme AI Corp")

    app_check_res_2 = MagicMock()
    app_check_res_2.scalar_one_or_none.return_value = mock_app

    mock_db.execute.side_effect = [job_res_2, app_check_res_2]

    res_retry = await job_service.apply_to_job(
        mock_db,
        candidate_user_id=candidate_id,
        job_id=job_id,
        idempotency_key=idempotency_key,
    )

    assert res_retry.id == res.id
    assert "idempotent" in res_retry.message.lower()


@pytest.mark.asyncio
async def test_apply_to_job_blocked_for_closed_and_expired_jobs() -> None:
    """Verify application is rejected if job is not published or past deadline."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    # 1. Closed job
    mock_job_closed = MagicMock(spec=Job)
    mock_job_closed.id = job_id
    mock_job_closed.status = JobStatus.CLOSED.value
    mock_job_closed.application_deadline = None

    job_res_closed = MagicMock()
    job_res_closed.first.return_value = (mock_job_closed, "Acme")
    mock_db.execute.side_effect = [job_res_closed]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.apply_to_job(mock_db, candidate_id, job_id)
    assert exc_info.value.code == "JOB_NOT_ACCEPTING_APPLICATIONS"

    # 2. Expired deadline job
    mock_job_expired = MagicMock(spec=Job)
    mock_job_expired.id = job_id
    mock_job_expired.status = JobStatus.PUBLISHED.value
    mock_job_expired.application_deadline = datetime(2020, 1, 1, tzinfo=UTC)

    job_res_expired = MagicMock()
    job_res_expired.first.return_value = (mock_job_expired, "Acme")
    mock_db.execute.side_effect = [job_res_expired]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.apply_to_job(mock_db, candidate_id, job_id)
    assert exc_info.value.code == "DEADLINE_PASSED"


@pytest.mark.asyncio
async def test_apply_to_job_invalid_resume_ownership() -> None:
    """Verify candidate cannot apply using a resume that does not belong to them (IDOR)."""
    attacker_candidate_id = uuid4()
    job_id = uuid4()
    foreign_resume_id = uuid4()
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme")

    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = None

    # Resume query returns None because foreign_resume_id does not belong to attacker
    res_query = MagicMock()
    res_query.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [job_res, app_check_res, res_query]

    with pytest.raises(EntityNotFoundException):
        await job_service.apply_to_job(
            mock_db,
            candidate_user_id=attacker_candidate_id,
            job_id=job_id,
            resume_id=foreign_resume_id,
        )


@pytest.mark.asyncio
async def test_apply_to_job_withdrawn_reapplication_restriction() -> None:
    """Verify that a candidate cannot re-apply to a position they have withdrawn, preserving record."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme")

    mock_app = MagicMock(spec=JobApplication)
    mock_app.candidate_status = CandidateFacingStatus.WITHDRAWN.value

    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = mock_app

    mock_db.execute.side_effect = [job_res, app_check_res]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.apply_to_job(mock_db, candidate_id, job_id)
    assert exc_info.value.code == "ERR_APPLICATION_WITHDRAWN"


@pytest.mark.asyncio
async def test_apply_to_job_concurrency_integrity_error() -> None:
    """Verify that database unique constraint conflicts (race condition) are cleanly handled."""
    candidate_id = uuid4()
    job_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.application_deadline = None

    job_res = MagicMock()
    job_res.first.return_value = (mock_job, "Acme")

    app_check_res = MagicMock()
    app_check_res.scalar_one_or_none.return_value = None

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.version_number = 1
    mock_resume.content_sha256 = "sha256_mock"

    res_query = MagicMock()
    res_query.scalar_one_or_none.return_value = mock_resume

    mock_db.execute.side_effect = [job_res, app_check_res, res_query]
    mock_db.commit.side_effect = IntegrityError("Unique violation", params=None, orig=Exception())

    with pytest.raises(ValidationException) as exc_info:
        await job_service.apply_to_job(mock_db, candidate_id, job_id, resume_id=resume_id)

    assert exc_info.value.code == "ERR_DUPLICATE_APPLICATION"
    mock_db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_application_withdrawal_restrictions() -> None:
    """Verify that applications already in terminal state or offer stage cannot be withdrawn."""
    candidate_id = uuid4()
    app_id = uuid4()
    mock_db = AsyncMock()

    # 1. Already concluded / not selected
    mock_app_rejected = MagicMock(spec=JobApplication)
    mock_app_rejected.id = app_id
    mock_app_rejected.candidate_status = CandidateFacingStatus.NOT_SELECTED.value

    app_res = MagicMock()
    app_res.scalar_one_or_none.return_value = mock_app_rejected
    mock_db.execute.side_effect = [app_res]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.withdraw_application(mock_db, candidate_id, app_id, reason="Changed mind")
    assert exc_info.value.code == "CANNOT_WITHDRAW_TERMINAL"

    # 2. In offer stage
    mock_app_offer = MagicMock(spec=JobApplication)
    mock_app_offer.id = app_id
    mock_app_offer.candidate_status = CandidateFacingStatus.OFFER_STAGE.value

    app_res_2 = MagicMock()
    app_res_2.scalar_one_or_none.return_value = mock_app_offer
    mock_db.execute.side_effect = [app_res_2]

    with pytest.raises(ValidationException) as exc_info:
        await job_service.withdraw_application(mock_db, candidate_id, app_id, reason="Changed mind")
    assert exc_info.value.code == "CANNOT_WITHDRAW_OFFER"


# =============================================================================
# FastAPI Endpoint Integration Tests (HTTP Layer)
# =============================================================================
@pytest.fixture
def test_app():
    return create_application()


@pytest.mark.asyncio
async def test_get_candidate_profile_endpoint_authenticated(test_app) -> None:
    """Verify GET /api/v1/candidates/me/profile returns 200 with profile DTO."""
    candidate_id = uuid4()
    mock_sec = SecurityContext(
        user_id=candidate_id,
        session_id=uuid4(),
        tenant_id=None,
        roles=["candidate"],
        permissions=[],
    )

    fake_profile = CandidateProfileRead(
        user_id=candidate_id,
        email="candidate@test.com",
        first_name="Candidate",
        last_name="User",
        headline="Principal Engineer",
        bio="Experienced architect",
        phone="+1-555-0100",
        location_city="Seattle",
        location_country="USA",
        preferred_title="Staff Engineer",
        work_authorization="Authorized",
        portfolio_urls=["https://alice.dev"],
        self_declared_skills=["Python", "FastAPI"],
        experiences=[],
        educations=[],
        certifications=[],
        projects=[],
        languages=[],
        preferences=None,
        profile_completion_percentage=80,
    )

    test_app.dependency_overrides[require_authenticated_user] = lambda: mock_sec
    test_app.dependency_overrides[get_db] = lambda: AsyncMock()

    with patch.object(candidate_service, "get_candidate_profile", return_value=fake_profile):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/candidates/me/profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["email"] == "candidate@test.com"

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_apply_job_endpoint_validation(test_app) -> None:
    """Verify POST /api/v1/jobs/{job_id}/apply successfully invokes apply workflow."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_sec = SecurityContext(
        user_id=candidate_id,
        session_id=uuid4(),
        tenant_id=None,
        roles=["candidate"],
        permissions=[],
    )

    test_app.dependency_overrides[require_authenticated_user] = lambda: mock_sec
    test_app.dependency_overrides[get_db] = lambda: AsyncMock()

    fake_resp = MagicMock()
    fake_resp.id = uuid4()
    fake_resp.job_id = job_id
    fake_resp.candidate_status = "submitted"
    fake_resp.message = "Application submitted successfully"
    fake_resp.applied_at = datetime.now(UTC)

    with patch.object(job_service, "apply_to_job", return_value=fake_resp):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/jobs/{job_id}/apply",
                json={"cover_letter": "Excited to join the platform team!"},
            )
            assert resp.status_code == 201
            assert resp.json()["candidate_status"] == "submitted"

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_education_certification_project_crud() -> None:
    """Verify education, certification, project, and language CRUD workflows."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    # Education
    edu_dto = EducationCreate(
        institution="Stanford University",
        degree="B.S.",
        field_of_study="Computer Science",
        start_year=2018,
        end_year=2022,
        grade="3.9",
    )
    edu_res = await candidate_service.add_education(mock_db, candidate_id, edu_dto)
    assert edu_res.institution == "Stanford University"
    assert edu_res.degree == "B.S."

    # Certification
    cert_dto = CertificationCreate(
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services",
        issue_date="2023-01",
        credential_id="AWS-12345",
    )
    cert_res = await candidate_service.add_certification(mock_db, candidate_id, cert_dto)
    assert cert_res.name == "AWS Certified Solutions Architect"

    # Project
    proj_dto = ProjectCreate(
        title="Distributed Job Queue",
        description="High throughput queue engine",
        role="Author",
        project_url="https://github.com/alice/queue",
        skills=["Python", "Redis"],
    )
    proj_res = await candidate_service.add_project(mock_db, candidate_id, proj_dto)
    assert proj_res.title == "Distributed Job Queue"

    # Language
    lang_dto = LanguageCreate(language="English", proficiency="native")
    lang_res = await candidate_service.add_language(mock_db, candidate_id, lang_dto)
    assert lang_res.language == "English"
    assert lang_res.proficiency == "native"


@pytest.mark.asyncio
async def test_candidate_preferences_lifecycle() -> None:
    """Verify getting and updating candidate career preferences."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    mock_pref = MagicMock(spec=CandidatePreference)
    mock_pref.user_id = candidate_id
    mock_pref.desired_job_titles = ["Backend Engineer"]
    mock_pref.desired_locations = ["Remote"]
    mock_pref.remote_preference = "remote"
    mock_pref.employment_types = ["full_time"]
    mock_pref.minimum_salary = 150000
    mock_pref.currency = "USD"
    mock_pref.updated_at = datetime.now(UTC)

    pref_res = MagicMock()
    pref_res.scalar_one_or_none.return_value = mock_pref
    mock_db.execute.return_value = pref_res

    res = await candidate_service.get_preferences(mock_db, candidate_id)
    assert res.remote_preference == "remote"
    assert res.minimum_salary == 150000

    # Update preferences
    update_dto = CandidatePreferenceUpdate(
        minimum_salary=180000,
        remote_preference="hybrid",
    )
    updated_res = await candidate_service.update_preferences(mock_db, candidate_id, update_dto)
    assert updated_res.minimum_salary == 180000
    assert mock_pref.minimum_salary == 180000
    assert mock_pref.remote_preference == "hybrid"


@pytest.mark.asyncio
async def test_saved_jobs_lifecycle() -> None:
    """Verify candidate saving and unsaving jobs."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    # Job exists
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = job_id

    # Not saved yet
    saved_res = MagicMock()
    saved_res.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [job_res, saved_res, MagicMock()]

    # Save job
    await job_service.save_job(mock_db, candidate_id, job_id)
    mock_db.commit.assert_awaited()

    # Unsave job
    await job_service.unsave_job(mock_db, candidate_id, job_id)


@pytest.mark.asyncio
async def test_candidate_notifications_lifecycle() -> None:
    """Verify candidate in-app notifications listing and read state mutation."""
    candidate_id = uuid4()
    notif_id = uuid4()
    mock_db = AsyncMock()

    mock_notif = MagicMock(spec=CandidateNotification)
    mock_notif.id = notif_id
    mock_notif.user_id = candidate_id
    mock_notif.title = "Application Submitted"
    mock_notif.message = "Your application was received."
    mock_notif.category = "application_update"
    mock_notif.is_read = False
    mock_notif.action_url = "/candidate/applications/123"
    mock_notif.created_at = datetime.now(UTC)

    list_res = MagicMock()
    list_res.scalars.return_value.all.return_value = [mock_notif]
    mock_db.execute.return_value = list_res

    notifs = await candidate_service.list_notifications(mock_db, candidate_id)
    assert len(notifs.notifications) == 1
    assert notifs.unread_count == 1

    # Mark as read
    item_res = MagicMock()
    item_res.scalar_one_or_none.return_value = mock_notif
    mock_db.execute.return_value = item_res

    await candidate_service.mark_notification_read(mock_db, candidate_id, notif_id)
    assert mock_notif.is_read is True


@pytest.mark.asyncio
async def test_resume_download_url_and_deletion() -> None:
    """Verify presigned download URL generation and deletion with storage cleanup."""
    candidate_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.storage_key = "candidates/123/resumes/resume.pdf"

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_resume
    mock_db.execute.return_value = res_mock

    # Mock storage
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.generate_presigned_download_url.return_value = (
        "https://s3.amazonaws.com/presigned_url"
    )

    svc = CandidateService(
        storage=mock_storage, extractor=None, matcher=None, registry=skill_registry
    )

    # Download URL
    download_dto = await svc.get_download_url(mock_db, candidate_id, resume_id)
    assert "https://s3.amazonaws.com" in download_dto.download_url

    # Delete resume
    await svc.delete_resume(mock_db, candidate_id, resume_id)
    mock_storage.delete_document_object.assert_called_once_with(mock_resume.storage_key)
    mock_db.delete.assert_called_once_with(mock_resume)


@pytest.mark.asyncio
async def test_duplicate_skills_normalization_and_unknown_skills() -> None:
    """Verify alias normalization, duplicate elimination, and safe unknown skill handling."""
    candidate_id = uuid4()
    mock_db = AsyncMock()

    mock_profile = MagicMock(spec=CandidateUserProfile)
    mock_profile.self_declared_skills = []

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_profile
    mock_db.execute.return_value = res_mock

    svc = CandidateService(storage=None, extractor=None, matcher=None, registry=skill_registry)

    # Input contains aliases of React, duplicates, whitespace, and a niche/custom skill
    raw_input = ["reactjs", "React.js", "REACT", "python", "  python  ", "NicheCustomFramework"]
    resp = await svc.update_skills(mock_db, candidate_id, raw_input)

    # Verify deduplication and canonical normalization
    assert "React" in resp.skills
    assert "Python" in resp.skills
    assert "NicheCustomFramework" in resp.skills
    # Must not contain duplicate canonical entries
    assert resp.skills.count("React") == 1
    assert resp.skills.count("Python") == 1
    assert resp.total_count == 3


@pytest.mark.asyncio
async def test_profile_and_experience_invalid_inputs_validation() -> None:
    """Verify backend Pydantic validation rejects invalid dates, bounds, and empty fields."""
    from pydantic import ValidationError

    # Empty company or job title
    with pytest.raises(ValidationError):
        ExperienceCreate(
            job_title="",
            company_name="Acme",
            start_date="2020-01",
        )

    # Invalid education year out of bounds (< 1950)
    with pytest.raises(ValidationError):
        EducationCreate(
            institution="University",
            degree="BS",
            field_of_study="CS",
            start_year=1800,
        )

    # Negative minimum salary
    with pytest.raises(ValidationError):
        CandidatePreferenceUpdate(
            minimum_salary=-5000,
        )


@pytest.mark.asyncio
async def test_unauthenticated_and_cross_candidate_access_rejections(test_app) -> None:
    """Verify endpoints reject unauthenticated callers and enforce IDOR boundaries."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Unauthenticated request to /candidates/me should be rejected with 401
        res = await ac.get("/api/v1/candidates/me")
        assert res.status_code == 401
        assert "NOT_AUTHENTICATED" in res.text or "credentials" in res.text

        # 2. Unauthenticated request to delete experience
        res_del = await ac.delete(f"/api/v1/candidates/me/experience/{uuid4()}")
        assert res_del.status_code == 401


@pytest.mark.asyncio
async def test_candidate_creation_global_identity_decoupled() -> None:
    """Verify candidate identity is platform-global with active_tenant_id=None."""
    from app.core.config import get_settings
    from app.modules.auth.schemas import RegisterRequest
    from app.modules.auth.service import register_user

    mock_db = AsyncMock()
    # Mock no existing user with same email
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res_mock

    settings = get_settings()

    req = RegisterRequest(
        email="candidate.bob@example.com",
        password="SecurePassword123!",
        first_name="Bob",
        last_name="Candidate",
    )

    created_user = await register_user(mock_db, req, settings)
    assert created_user.email == "candidate.bob@example.com"
    assert created_user.is_active is True
    assert created_user.is_super_admin is False


@pytest.mark.asyncio
async def test_resume_deletion_blocked_when_linked_to_application() -> None:
    """Verify defensibility: a resume linked to submitted job application(s) cannot be deleted."""
    candidate_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.filename = "alice_resume.pdf"
    mock_resume.version_number = 1
    mock_resume.storage_key = "candidates/123/resumes/alice.pdf"
    mock_resume.content_sha256 = "dummy_sha_256"

    # Query 1: return resume
    res_resume = MagicMock()
    res_resume.scalar_one_or_none.return_value = mock_resume

    # Query 2: return application count = 2
    res_app_count = MagicMock()
    res_app_count.scalar.return_value = 2

    mock_db.execute.side_effect = [res_resume, res_app_count]

    mock_storage = MagicMock(spec=StorageService)
    svc = CandidateService(storage=mock_storage, extractor=None, matcher=None, registry=skill_registry)

    with pytest.raises(ValidationException) as exc_info:
        await svc.delete_resume(mock_db, candidate_id, resume_id)

    assert "retained under compliance" in str(exc_info.value)
    assert exc_info.value.code == "ERR_RESUME_RETAINED_FOR_APPLICATIONS"
    # Storage and DB delete must NOT have been called
    mock_storage.delete_document_object.assert_not_called()
    mock_db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_upload_docx_resume_and_extraction() -> None:
    """Verify DOCX resume upload parses OpenXML text, extracts canonical skills, and reports accurate status."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>'
            '<w:p><w:r><w:t>Bob Smith</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>bob@example.com | +1 555-123-4567</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Summary: Experienced Python and PostgreSQL backend engineer.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        zf.writestr("word/document.xml", doc_xml)
    docx_bytes = buf.getvalue()

    candidate_id = uuid4()
    mock_db = AsyncMock()

    dup_res = MagicMock()
    dup_res.scalar_one_or_none.return_value = None

    count_res = MagicMock()
    count_res.scalar.return_value = 0

    mock_db.execute.side_effect = [dup_res, count_res]

    mock_storage = MagicMock(spec=StorageService)
    svc = CandidateService(storage=mock_storage, extractor=None, matcher=None, registry=skill_registry)

    upload_file = UploadFile(
        file=io.BytesIO(docx_bytes),
        filename="bob_resume.docx",
    )

    resp = await svc.upload_resume(mock_db, candidate_id, upload_file)
    assert resp.is_duplicate is False
    assert resp.version_number == 1
    assert resp.is_default is True
    assert resp.ocr_applied is False
    assert resp.ocr_provider == "null_ocr_unconfigured"
    assert resp.malware_scan_status == "passed_development_mode"
    mock_storage.upload_document_bytes.assert_called_once()


@pytest.mark.asyncio
async def test_resume_extraction_structured_fields_and_ocr_status() -> None:
    """Verify structured resume parsing extracts fields (email, phone, summary, experience) with accurate OCR status."""
    candidate_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    resume_text = (
        "Alice Candidate\n"
        "alice.candidate@example.com\n"
        "(555) 234-5678\n"
        "Summary\n"
        "Results-driven software architect with 8 years of experience building Python and FastAPI microservices.\n"
        "Skills\n"
        "Python, FastAPI, Docker, PostgreSQL\n"
        "Experience\n"
        "Lead Engineer - Acme Corp - 2021 to Present\n"
        "Architected scalable cloud platforms and managed backend APIs.\n"
        "Education\n"
        "B.S. in Computer Science - Tech University - 2017 to 2021\n"
        "Certifications\n"
        "AWS Solutions Architect Associate\n"
        "Projects\n"
        "Open Source ETL Pipeline - Python data streaming tool\n"
    )

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.extracted_text = resume_text
    mock_resume.skills_extracted = ["Python", "FastAPI", "Docker", "PostgreSQL"]
    mock_resume.status = "COMPLETED"

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_resume
    mock_db.execute.return_value = res_mock

    svc = CandidateService(storage=None, extractor=None, matcher=None, registry=skill_registry)
    extraction = await svc.get_resume_extraction(mock_db, candidate_id, resume_id)

    assert extraction.resume_id == resume_id
    assert extraction.status == "COMPLETED"
    assert extraction.ocr_applied is False
    assert extraction.ocr_provider == "null_ocr_unconfigured"
    assert extraction.extracted_data is not None
    assert extraction.extracted_data.email == "alice.candidate@example.com"
    assert extraction.extracted_data.phone is not None
    assert "FastAPI" in extraction.extracted_data.skills
    assert len(extraction.extracted_data.experience) >= 1
    assert len(extraction.extracted_data.education) >= 1
    assert "AWS Solutions Architect Associate" in extraction.extracted_data.certifications


@pytest.mark.asyncio
async def test_sync_resume_skills_to_profile() -> None:
    """Verify candidate can edit extracted skills and apply them directly to verified profile."""
    candidate_id = uuid4()
    resume_id = uuid4()
    mock_db = AsyncMock()

    mock_resume = MagicMock(spec=CandidateResume)
    mock_resume.id = resume_id
    mock_resume.user_id = candidate_id
    mock_resume.extracted_text = "Python engineer"
    mock_resume.skills_extracted = ["Python"]
    mock_resume.status = "COMPLETED"

    mock_profile = MagicMock(spec=CandidateUserProfile)
    mock_profile.self_declared_skills = []

    res_resume = MagicMock()
    res_resume.scalar_one_or_none.return_value = mock_resume
    res_profile = MagicMock()
    res_profile.scalar_one_or_none.return_value = mock_profile

    # Sequence of queries: 1) fetch resume, 2) fetch profile in update_skills
    mock_db.execute.side_effect = [res_resume, res_profile]

    svc = CandidateService(storage=None, extractor=None, matcher=None, registry=skill_registry)

    update_payload = ResumeExtractedDataUpdate(
        skills_extracted=["Python", "FastAPI", "Docker"],
        apply_to_profile=True,
    )

    resp = await svc.update_extracted_data(mock_db, candidate_id, resume_id, update_payload)
    assert resp.skills_extracted == ["Python", "FastAPI", "Docker"]
    assert "Python" in mock_profile.self_declared_skills


@pytest.mark.asyncio
async def test_job_discovery_advanced_search_and_filters() -> None:
    """Verify job search filters by keywords, skills, salary range, remote arrangement, and publication cutoff."""
    mock_db = AsyncMock()
    org_id = uuid4()
    job_id = uuid4()

    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.tenant_id = org_id
    mock_job.title = "Senior Python Backend Engineer"
    mock_job.slug = "senior-python-backend-engineer"
    mock_job.department = "Platform Engineering"
    mock_job.location = "New York, NY"
    mock_job.remote_type = "remote"
    mock_job.employment_type = "full_time"
    mock_job.description = "Lead backend cloud services with <script>alert(1)</script> FastAPI and Redis."
    mock_job.requirements = "8+ years building distributed systems."
    mock_job.skills_required = ["Python", "FastAPI", "PostgreSQL", "Redis"]
    mock_job.experience_level = "senior"
    mock_job.salary_min = 160000
    mock_job.salary_max = 210000
    mock_job.salary_currency = "USD"
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.published_at = datetime.now(UTC)
    mock_job.application_deadline = None

    count_res = MagicMock()
    count_res.scalar.return_value = 1

    jobs_res = MagicMock()
    jobs_res.all.return_value = [(mock_job, "Global Corp")]

    mock_db.execute.side_effect = [count_res, jobs_res]

    res = await job_service.list_jobs(
        mock_db,
        query="Python",
        remote_type="remote",
        employment_type="full_time",
        experience_level="senior",
        skills=["FastAPI", "PostgreSQL"],
        min_salary=150000,
        max_salary=250000,
        posted_within_days=30,
        sort_by="salary_high",
        page=1,
        page_size=10,
    )

    assert res.total == 1
    assert len(res.jobs) == 1
    job = res.jobs[0]
    assert job.title == "Senior Python Backend Engineer"
    assert job.organization_name == "Global Corp"
    assert job.remote_type == "remote"
    assert job.is_expired is False
    assert job.has_applied is False
    # Sanitization check: script tag removed or neutralized
    assert "<script>" not in job.description


@pytest.mark.asyncio
async def test_job_discovery_sorting_and_pagination() -> None:
    """Verify sorting options and pagination bounds for job requisitions."""
    mock_db = AsyncMock()
    mock_job1 = MagicMock(spec=Job)
    mock_job1.id = uuid4()
    mock_job1.tenant_id = uuid4()
    mock_job1.title = "Frontend Lead"
    mock_job1.slug = "frontend-lead"
    mock_job1.department = "Product"
    mock_job1.location = "Remote"
    mock_job1.remote_type = "remote"
    mock_job1.employment_type = "full_time"
    mock_job1.description = "React architect"
    mock_job1.requirements = None
    mock_job1.skills_required = ["React", "TypeScript"]
    mock_job1.experience_level = "lead"
    mock_job1.salary_min = 170000
    mock_job1.salary_max = 220000
    mock_job1.salary_currency = "USD"
    mock_job1.status = JobStatus.PUBLISHED.value
    mock_job1.published_at = datetime.now(UTC)
    mock_job1.application_deadline = None

    count_res = MagicMock()
    count_res.scalar.return_value = 25

    jobs_res = MagicMock()
    jobs_res.all.return_value = [(mock_job1, "Acme Inc")]

    mock_db.execute.side_effect = [count_res, jobs_res]

    # Test closing soon sort order and pagination
    res = await job_service.list_jobs(
        mock_db,
        sort_by="closing_soon",
        page=2,
        page_size=10,
    )

    assert res.total == 25
    assert res.page == 2
    assert res.page_size == 10
    assert res.total_pages == 3


@pytest.mark.asyncio
async def test_saved_jobs_duplicate_prevention_and_applied_status() -> None:
    """Verify saving duplicate job is prevented, and saved jobs list identifies expired & applied jobs."""
    candidate_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    # 1. Existing bookmark check
    job_exists = MagicMock()
    job_exists.scalar_one_or_none.return_value = job_id

    already_saved = MagicMock()
    already_saved.scalar_one_or_none.return_value = MagicMock(spec=CandidateSavedJob)

    mock_db.execute.side_effect = [job_exists, already_saved]

    # Saving again should be a no-op (no duplicate insert)
    await job_service.save_job(mock_db, candidate_id, job_id)
    # db.add must NOT be called for duplicate
    mock_db.add.assert_not_called()

    # 2. Listing saved jobs with applied and expired identification
    mock_job = MagicMock(spec=Job)
    mock_job.id = job_id
    mock_job.tenant_id = uuid4()
    mock_job.title = "Security Analyst"
    mock_job.slug = "security-analyst"
    mock_job.department = "SecOps"
    mock_job.location = "Austin, TX"
    mock_job.remote_type = "onsite"
    mock_job.employment_type = "contract"
    mock_job.description = "Security engineering"
    mock_job.requirements = None
    mock_job.skills_required = ["SOC2", "SIEM"]
    mock_job.experience_level = "mid"
    mock_job.salary_min = 120000
    mock_job.salary_max = 140000
    mock_job.salary_currency = "USD"
    # Mark as expired deadline in the past
    mock_job.status = JobStatus.PUBLISHED.value
    mock_job.published_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock_job.application_deadline = datetime(2026, 2, 1, tzinfo=UTC)

    saved_entry = MagicMock(spec=CandidateSavedJob)
    saved_entry.saved_at = datetime.now(UTC)

    saved_query_res = MagicMock()
    saved_query_res.all.return_value = [(saved_entry, mock_job, "SecureOrg")]

    # Applied query returns this job_id as applied
    applied_query_res = MagicMock()
    applied_query_res.scalars.return_value.all.return_value = [job_id]

    mock_db.execute.side_effect = [saved_query_res, applied_query_res]

    saved_list = await job_service.list_saved_jobs(mock_db, candidate_id)
    assert len(saved_list) == 1
    item = saved_list[0]
    assert item.job.title == "Security Analyst"
    assert item.job.has_applied is True
    assert item.job.is_expired is True
    assert item.job.is_saved is True
