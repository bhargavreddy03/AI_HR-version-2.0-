"""FastAPI endpoints for Job Discovery, Search, and Candidate Applications.

Conforms to Step 4.1 specifications.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import SecurityContext
from app.modules.auth.dependencies import (
    authenticate_request_pipeline,
    require_authenticated_user,
)
from app.modules.jobs.schemas import (
    ApplicationSubmitResponse,
    JobApplyRequest,
    JobListResponse,
    JobRead,
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
async def list_jobs(
    query: str | None = Query(None, description="Keyword search query"),
    department: str | None = Query(None, description="Department filter"),
    location: str | None = Query(None, description="Location filter"),
    remote_type: str | None = Query(None, description="Remote arrangement: remote, hybrid, onsite"),
    employment_type: str | None = Query(
        None, description="Employment type: full_time, part_time, contract"
    ),
    experience_level: str | None = Query(
        None, description="Experience level: entry, mid, senior, lead"
    ),
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
        page=page,
        page_size=page_size,
    )


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
    """Retrieve complete job description, required skills, and candidate status."""
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
