"""FastAPI endpoints for Job Discovery, Search, and Candidate Applications.

Conforms to Step 4.1 specifications.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import SecurityContext
from app.modules.auth.dependencies import (
    authenticate_request_pipeline,
    require_authenticated_user,
)
from app.modules.jobs.schemas import (
    ApplicationSubmitResponse,
    JobApplicationRead,
    JobApplyRequest,
    JobListResponse,
    JobRead,
    SavedJobRead,
)
from app.modules.jobs.service import job_service

logger = logging.getLogger(__name__)

job_router = APIRouter(prefix="/jobs", tags=["Job Discovery & Applications"])


async def get_optional_candidate_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UUID | None:
    """Resolve authenticated candidate user ID if credentials present, otherwise None."""
    try:
        sec = await authenticate_request_pipeline(request=request, db=db)
        return sec.user_id
    except Exception:
        return None


@job_router.get(
    "",
    response_model=JobListResponse,
    summary="Search, filter, and paginate published job requisitions",
)
@job_router.get(
    "/search",
    response_model=JobListResponse,
    summary="Search, filter, and paginate published job requisitions (alias)",
)
async def list_jobs(
    query: str | None = Query(None, description="Keyword search query"),
    department: str | None = Query(None, description="Department filter"),
    location: str | None = Query(None, description="Location filter"),
    remote_type: str | None = Query(None, description="Remote arrangement: remote, hybrid, onsite"),
    employment_type: str | None = Query(
        None, description="Employment type: full_time, part_time, contract, internship"
    ),
    experience_level: str | None = Query(
        None, description="Experience level: entry, mid, senior, lead, executive"
    ),
    skills: str | None = Query(None, description="Comma-separated skill requirements"),
    min_salary: int | None = Query(None, ge=0, description="Minimum salary filter"),
    max_salary: int | None = Query(None, ge=0, description="Maximum salary filter"),
    posted_within_days: int | None = Query(None, ge=1, le=365, description="Posted within past N days"),
    sort_by: str = Query("recent", description="Sort order: recent, closing_soon, salary_high"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    candidate_id: UUID | None = Depends(get_optional_candidate_user),
) -> JobListResponse:
    """Browse and filter active opportunities with saved and applied badges for candidate."""
    return await job_service.list_jobs(
        db=db,
        candidate_user_id=candidate_id,
        query=query,
        department=department,
        location=location,
        remote_type=remote_type,
        employment_type=employment_type,
        experience_level=experience_level,
        skills=skills,
        min_salary=min_salary,
        max_salary=max_salary,
        posted_within_days=posted_within_days,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# Saved Jobs Endpoints (/api/v1/jobs/saved & /jobs/{id}/save)
# =============================================================================
@job_router.get(
    "/saved",
    response_model=list[SavedJobRead],
    summary="List all jobs bookmarked by candidate",
)
async def list_saved_jobs(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> list[SavedJobRead]:
    return await job_service.list_saved_jobs(db, sec.user_id)


@job_router.post(
    "/{job_id}/save",
    status_code=status.HTTP_201_CREATED,
    summary="Bookmark job",
)
async def save_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> dict[str, str]:
    await job_service.save_job(db, sec.user_id, job_id)
    return {"message": "Job bookmarked successfully"}


@job_router.delete(
    "/{job_id}/save",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove bookmark for job",
)
async def unsave_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await job_service.unsave_job(db, sec.user_id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@job_router.get(
    "/applications/me",
    response_model=list[JobApplicationRead],
    summary="List applications submitted by candidate",
)
async def list_my_applications(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> list[JobApplicationRead]:
    return await job_service.list_candidate_applications(db, sec.user_id)


@job_router.get(
    "/{job_id}",
    response_model=JobRead,
    summary="Retrieve detailed published job requisition",
)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    candidate_id: UUID | None = Depends(get_optional_candidate_user),
) -> JobRead:
    """Retrieve complete authorized job description, required skills, and candidate status."""
    return await job_service.get_job(db, job_id, candidate_user_id=candidate_id)


@job_router.post(
    "/{job_id}/apply",
    response_model=ApplicationSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit candidate application for a published job requisition",
)
async def apply_to_job(
    job_id: UUID,
    payload: JobApplyRequest,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ApplicationSubmitResponse:
    """Submit application attaching selected resume version and optional cover letter."""
    return await job_service.apply_to_job(
        db=db,
        candidate_user_id=sec.user_id,
        job_id=job_id,
        resume_id=payload.resume_id,
        cover_letter=payload.cover_letter,
    )
