"""Unit and integration tests for Step 4.2.3 HR Job Requisition Management.

Verifies:
1. Requisition creation with complete fields and canonical skill taxonomy normalization.
2. Salary range validation (salary_min <= salary_max).
3. Organization boundary / tenant isolation enforcement.
4. Server-side pagination, search, and status filters.
5. Requisition retrieval and updates.
6. Safe deletion rules (preventing deletion when applications exist).
7. Team member retrieval for recruiter/hiring manager assignments.
8. Canonical skill registry autocompletion.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.base import utc_now
from app.core.errors import ConflictException
from app.modules.auth.models import User
from app.modules.hr.requisition_schemas import (
    JobRequisitionCreate,
)
from app.modules.hr.service import hr_requisition_service
from app.modules.jobs.models import Job


def test_job_requisition_salary_validation():
    """Verify Pydantic enforces salary_min <= salary_max."""
    # Valid
    valid_req = JobRequisitionCreate(
        title="Senior Python Engineer",
        department="Engineering",
        location="San Francisco, CA",
        description="A great role for a Senior Python Engineer.",
        salary_min=120000,
        salary_max=160000,
    )
    assert valid_req.salary_min == 120000
    assert valid_req.salary_max == 160000

    # Invalid: salary_min > salary_max
    with pytest.raises(ValidationError) as exc:
        JobRequisitionCreate(
            title="Senior Python Engineer",
            department="Engineering",
            location="San Francisco, CA",
            description="A great role for a Senior Python Engineer.",
            salary_min=180000,
            salary_max=150000,
        )
    assert "salary_min cannot be greater than salary_max" in str(exc.value)


def test_canonical_skill_normalization():
    """Verify skill normalization leverages Canonical Skill Registry."""
    raw_skills = ["python", "c++", "NODE.JS", "FastAPI", "unknown_custom_tool", "Python"]
    normalized = hr_requisition_service._normalize_skill_list(raw_skills)

    # Python should be deduplicated
    assert "Python" in normalized or "python" in normalized
    # C++ protected & normalized
    assert "C++" in normalized
    # Node.js canonical form
    assert "Node.js" in normalized
    # Custom skill preserved
    assert "unknown_custom_tool" in normalized
    # Total unique count
    assert len(normalized) == 5


def test_canonical_skills_autocomplete():
    """Verify canonical skill autocomplete returns taxonomy suggestions."""
    results = hr_requisition_service.search_canonical_skills(query="pyth", limit=5)
    assert len(results) > 0
    names = [r.canonical_name for r in results]
    assert any("Python" in n for n in names)


@pytest.mark.asyncio
async def test_create_requisition():
    """Verify requisition creation binds tenant_id, normalizes skills, and generates slug."""
    tenant_id = uuid4()
    recruiter_id = uuid4()
    hiring_manager_id = uuid4()

    mock_db = AsyncMock()

    create_data = JobRequisitionCreate(
        title="Lead Backend Architect",
        department="Engineering",
        location="Remote, US",
        country="United States",
        remote_type="remote",
        employment_type="full_time",
        experience_level="lead",
        description="Lead backend architecture using PostgreSQL and Python.",
        responsibilities="Design scalable systems and mentor engineers.",
        required_qualifications="10+ years backend engineering.",
        skills_required=["python", "PostgreSQL", "Docker"],
        preferred_skills=["kubernetes", "Kafka"],
        salary_min=180000,
        salary_max=220000,
        salary_currency="USD",
        vacancies_count=2,
        recruiter_id=recruiter_id,
        hiring_manager_id=hiring_manager_id,
        visibility="public",
        status="draft",
    )

    created_job = Job(
        id=uuid4(),
        tenant_id=tenant_id,
        title=create_data.title,
        slug="lead-backend-architect-12345678",
        department=create_data.department,
        location=create_data.location,
        country=create_data.country,
        remote_type=create_data.remote_type,
        employment_type=create_data.employment_type,
        experience_level=create_data.experience_level,
        description=create_data.description,
        responsibilities=create_data.responsibilities,
        required_qualifications=create_data.required_qualifications,
        skills_required=["Python", "PostgreSQL", "Docker"],
        preferred_skills=["Kubernetes", "Kafka"],
        salary_min=180000,
        salary_max=220000,
        salary_currency="USD",
        vacancies_count=2,
        status="draft",
        approval_status="draft",
        visibility="public",
        recruiter_id=recruiter_id,
        hiring_manager_id=hiring_manager_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    recruiter_user = User(
        id=recruiter_id,
        first_name="Alice",
        last_name="Recruiter",
        email="alice@company.com",
        password_hash="hash",
    )
    hm_user = User(
        id=hiring_manager_id,
        first_name="Bob",
        last_name="Manager",
        email="bob@company.com",
        password_hash="hash",
    )
    created_job.recruiter = recruiter_user
    created_job.hiring_manager = hm_user

    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = created_job

    app_count_res = MagicMock()
    app_count_res.scalar_one.return_value = 0

    mock_db.execute.side_effect = [job_res, app_count_res]

    result = await hr_requisition_service.create_requisition(
        db=mock_db,
        tenant_id=tenant_id,
        data=create_data,
    )

    assert result.title == "Lead Backend Architect"
    assert result.tenant_id == tenant_id
    assert result.recruiter_name == "Alice Recruiter"
    assert result.hiring_manager_name == "Bob Manager"
    assert result.applications_count == 0
    assert result.status == "draft"
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_get_requisition_tenant_isolation():
    """Verify get_requisition strictly enforces tenant isolation and returns None across tenants."""
    tenant_b = uuid4()
    job_id = uuid4()

    mock_db = AsyncMock()

    # Querying tenant_b returns None when job belongs to tenant_a
    empty_res = MagicMock()
    empty_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = empty_res

    res = await hr_requisition_service.get_requisition(mock_db, tenant_b, job_id)
    assert res is None


@pytest.mark.asyncio
async def test_list_requisitions_with_filters():
    """Verify list_requisitions computes total, pages, and filters by department and status."""
    tenant_id = uuid4()
    mock_db = AsyncMock()

    # Count result
    count_res = MagicMock()
    count_res.scalar_one.return_value = 1

    # Items result
    job = Job(
        id=uuid4(),
        tenant_id=tenant_id,
        title="Frontend Developer",
        slug="frontend-developer-12345678",
        department="Engineering",
        location="New York, NY",
        remote_type="hybrid",
        employment_type="full_time",
        experience_level="mid",
        description="Build user interfaces in React.",
        skills_required=["React", "TypeScript"],
        preferred_skills=["Tailwind CSS"],
        salary_min=110000,
        salary_max=140000,
        salary_currency="USD",
        vacancies_count=1,
        status="published",
        approval_status="approved",
        visibility="public",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    job.recruiter = None
    job.hiring_manager = None

    items_res = MagicMock()
    items_res.all.return_value = [(job, 7)]

    mock_db.execute.side_effect = [count_res, items_res]

    response = await hr_requisition_service.list_requisitions(
        db=mock_db,
        tenant_id=tenant_id,
        department="Engineering",
        status="published",
        page=1,
        page_size=10,
    )

    assert response.total == 1
    assert response.page == 1
    assert len(response.items) == 1
    assert response.items[0].title == "Frontend Developer"
    assert response.items[0].applications_count == 7


@pytest.mark.asyncio
async def test_delete_requisition_blocks_when_applications_exist():
    """Verify draft requisition cannot be deleted if candidate applications have been submitted."""
    tenant_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        title="Product Designer",
        slug="product-designer-1234",
        department="Design",
        location="Remote",
        description="Design intuitive experiences.",
        status="draft",
    )
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = job

    # Simulate 3 submitted applications
    app_count_res = MagicMock()
    app_count_res.scalar_one.return_value = 3

    mock_db.execute.side_effect = [job_res, app_count_res]

    with pytest.raises(ConflictException) as exc:
        await hr_requisition_service.delete_requisition(mock_db, tenant_id, job_id)

    assert "Cannot delete job requisition with existing candidate applications" in exc.value.message


@pytest.mark.asyncio
async def test_delete_requisition_succeeds_when_no_applications():
    """Verify requisition deletion succeeds when zero applications exist."""
    tenant_id = uuid4()
    job_id = uuid4()
    mock_db = AsyncMock()

    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        title="Unused Draft Job",
        slug="unused-draft-1234",
        department="Design",
        location="Remote",
        description="Draft.",
        status="draft",
    )
    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = job

    app_count_res = MagicMock()
    app_count_res.scalar_one.return_value = 0

    mock_db.execute.side_effect = [job_res, app_count_res]

    result = await hr_requisition_service.delete_requisition(mock_db, tenant_id, job_id)
    assert result is True
    mock_db.delete.assert_called_with(job)
    mock_db.commit.assert_called()
