"""FastAPI endpoints for Candidate Portal: Profile, Resumes, Preferences, and Notifications.

Conforms strictly to Step 4.1 API Contracts.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import SecurityContext
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.candidates.schemas import (
    CandidateNotificationsResponse,
    CandidatePreferenceRead,
    CandidatePreferenceUpdate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    CandidateResumeRead,
    CandidateSkillsResponse,
    CandidateSkillsUpdate,
    CertificationCreate,
    CertificationRead,
    EducationCreate,
    EducationRead,
    EducationUpdate,
    ExperienceCreate,
    ExperienceRead,
    ExperienceUpdate,
    LanguageCreate,
    LanguageRead,
    ProjectCreate,
    ProjectRead,
    ResumeDownloadUrlResponse,
    ResumeExtractedDataUpdate,
    ResumeExtractionResponse,
    ResumeUploadResponse,
)
from app.modules.candidates.service import candidate_service
from app.modules.jobs.schemas import (
    ApplicationWithdrawRequest,
    JobApplicationRead,
    SavedJobRead,
)
from app.modules.jobs.service import job_service

logger = logging.getLogger(__name__)

candidate_router = APIRouter(prefix="/candidates", tags=["Candidate Portal"])
resume_router = APIRouter(prefix="/resumes", tags=["Candidate Resumes"])


# =============================================================================
# Candidate Profile Endpoints
# =============================================================================
@candidate_router.get(
    "/me",
    response_model=CandidateProfileRead,
    summary="Retrieve current authenticated candidate summary",
)
async def get_current_candidate(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateProfileRead:
    return await candidate_service.get_candidate_profile(db, sec.user_id)


@candidate_router.patch(
    "/me",
    response_model=CandidateProfileRead,
    summary="Update candidate profile summary",
)
async def patch_candidate(
    payload: CandidateProfileUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateProfileRead:
    return await candidate_service.update_candidate_profile(db, sec.user_id, payload)


@candidate_router.get(
    "/me/profile",
    response_model=CandidateProfileRead,
    summary="Retrieve aggregated candidate profile with completion score",
)
async def get_candidate_profile(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateProfileRead:
    return await candidate_service.get_candidate_profile(db, sec.user_id)


@candidate_router.put(
    "/me/profile",
    response_model=CandidateProfileRead,
    summary="Upsert candidate profile personal details",
)
async def update_candidate_profile(
    payload: CandidateProfileUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateProfileRead:
    return await candidate_service.update_candidate_profile(db, sec.user_id, payload)


# =============================================================================
# Work Experience Endpoints
# =============================================================================
@candidate_router.post(
    "/me/experience",
    response_model=ExperienceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add work experience entry",
)
async def add_experience(
    payload: ExperienceCreate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ExperienceRead:
    return await candidate_service.add_experience(db, sec.user_id, payload)


@candidate_router.put(
    "/me/experience/{id}",
    response_model=ExperienceRead,
    summary="Update work experience entry",
)
async def update_experience(
    id: UUID,
    payload: ExperienceUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ExperienceRead:
    return await candidate_service.update_experience(db, sec.user_id, id, payload)


@candidate_router.delete(
    "/me/experience/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete work experience entry",
)
async def delete_experience(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_experience(db, sec.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Education Endpoints
# =============================================================================
@candidate_router.post(
    "/me/education",
    response_model=EducationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add education entry",
)
async def add_education(
    payload: EducationCreate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> EducationRead:
    return await candidate_service.add_education(db, sec.user_id, payload)


@candidate_router.put(
    "/me/education/{id}",
    response_model=EducationRead,
    summary="Update education entry",
)
async def update_education(
    id: UUID,
    payload: EducationUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> EducationRead:
    return await candidate_service.update_education(db, sec.user_id, id, payload)


@candidate_router.delete(
    "/me/education/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete education entry",
)
async def delete_education(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_education(db, sec.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Certifications, Projects, Languages Endpoints
# =============================================================================
@candidate_router.post(
    "/me/certifications",
    response_model=CertificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add certification entry",
)
async def add_certification(
    payload: CertificationCreate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CertificationRead:
    return await candidate_service.add_certification(db, sec.user_id, payload)


@candidate_router.delete(
    "/me/certifications/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete certification entry",
)
async def delete_certification(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_certification(db, sec.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@candidate_router.post(
    "/me/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add portfolio project entry",
)
async def add_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ProjectRead:
    return await candidate_service.add_project(db, sec.user_id, payload)


@candidate_router.delete(
    "/me/projects/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete portfolio project entry",
)
async def delete_project(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_project(db, sec.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@candidate_router.post(
    "/me/languages",
    response_model=LanguageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add language entry",
)
async def add_language(
    payload: LanguageCreate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> LanguageRead:
    return await candidate_service.add_language(db, sec.user_id, payload)


@candidate_router.delete(
    "/me/languages/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete language entry",
)
async def delete_language(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_language(db, sec.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Skills & Preferences Endpoints
# =============================================================================
@candidate_router.post(
    "/me/skills",
    response_model=CandidateSkillsResponse,
    summary="Update candidate self-declared skills normalized against canonical taxonomy",
)
async def update_skills(
    payload: CandidateSkillsUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateSkillsResponse:
    return await candidate_service.update_skills(db, sec.user_id, payload.skills)


@candidate_router.get(
    "/me/preferences",
    response_model=CandidatePreferenceRead,
    summary="Retrieve candidate employment preferences",
)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidatePreferenceRead:
    return await candidate_service.get_preferences(db, sec.user_id)


@candidate_router.patch(
    "/me/preferences",
    response_model=CandidatePreferenceRead,
    summary="Update candidate employment preferences",
)
async def update_preferences(
    payload: CandidatePreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidatePreferenceRead:
    return await candidate_service.update_preferences(db, sec.user_id, payload)


# =============================================================================
# Saved Jobs Endpoints
# =============================================================================
@candidate_router.get(
    "/me/saved-jobs",
    response_model=list[SavedJobRead],
    summary="List jobs bookmarked by candidate",
)
async def list_saved_jobs(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> list[SavedJobRead]:
    return await job_service.list_saved_jobs(db, sec.user_id)


@candidate_router.post(
    "/me/saved-jobs/{job_id}",
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


@candidate_router.delete(
    "/me/saved-jobs/{job_id}",
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


# =============================================================================
# Candidate Applications Tracking Endpoints
# =============================================================================
@candidate_router.get(
    "/me/applications",
    response_model=list[JobApplicationRead],
    summary="List all applications submitted by the candidate",
)
async def list_applications(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> list[JobApplicationRead]:
    return await job_service.list_candidate_applications(db, sec.user_id)


@candidate_router.get(
    "/me/applications/{application_id}",
    response_model=JobApplicationRead,
    summary="Retrieve application details with timeline",
)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> JobApplicationRead:
    return await job_service.get_candidate_application(db, sec.user_id, application_id)


@candidate_router.post(
    "/me/applications/{application_id}/withdraw",
    response_model=JobApplicationRead,
    summary="Withdraw submitted application with reason",
)
async def withdraw_application(
    application_id: UUID,
    payload: ApplicationWithdrawRequest,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> JobApplicationRead:
    return await job_service.withdraw_application(db, sec.user_id, application_id, payload.reason)


# =============================================================================
# Candidate Notifications Endpoints
# =============================================================================
@candidate_router.get(
    "/me/notifications",
    response_model=CandidateNotificationsResponse,
    summary="Retrieve candidate notifications",
)
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateNotificationsResponse:
    return await candidate_service.list_notifications(db, sec.user_id)


@candidate_router.patch(
    "/me/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.mark_notification_read(db, sec.user_id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@candidate_router.post(
    "/me/notifications/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.mark_all_notifications_read(db, sec.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Candidate Resumes Endpoints (/api/v1/resumes)
# =============================================================================
@resume_router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest candidate resume PDF or DOCX",
)
@resume_router.post(
    "/me/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest candidate resume PDF or DOCX (/me alias)",
)
async def upload_resume(
    response: Response,
    file: UploadFile = File(..., description="Resume PDF or DOCX document binary payload"),
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ResumeUploadResponse:
    res = await candidate_service.upload_resume(db, sec.user_id, file)
    if res.is_duplicate:
        response.status_code = status.HTTP_200_OK
    return res


@resume_router.get(
    "",
    response_model=list[CandidateResumeRead],
    summary="List all candidate resumes with versions",
)
@resume_router.get(
    "/me",
    response_model=list[CandidateResumeRead],
    summary="List all candidate resumes with versions (/me alias)",
)
async def list_resumes(
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> list[CandidateResumeRead]:
    return await candidate_service.list_resumes(db, sec.user_id)


@resume_router.get(
    "/{resume_id}",
    response_model=CandidateResumeRead,
    summary="Retrieve candidate resume metadata",
)
@resume_router.get(
    "/me/{resume_id}",
    response_model=CandidateResumeRead,
    summary="Retrieve candidate resume metadata (/me alias)",
)
async def get_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateResumeRead:
    return await candidate_service.get_resume(db, sec.user_id, resume_id)


@resume_router.get(
    "/{resume_id}/status",
    response_model=CandidateResumeRead,
    summary="Retrieve candidate resume lifecycle status",
)
@resume_router.get(
    "/me/{resume_id}/status",
    response_model=CandidateResumeRead,
    summary="Retrieve candidate resume lifecycle status (/me alias)",
)
async def get_resume_status(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateResumeRead:
    return await candidate_service.get_resume(db, sec.user_id, resume_id)


@resume_router.get(
    "/{resume_id}/extraction",
    response_model=ResumeExtractionResponse,
    summary="Retrieve extracted text, skills, and structured profile fields preview",
)
@resume_router.get(
    "/me/{resume_id}/extraction",
    response_model=ResumeExtractionResponse,
    summary="Retrieve extracted text, skills, and structured profile fields preview (/me alias)",
)
async def get_resume_extraction(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ResumeExtractionResponse:
    return await candidate_service.get_resume_extraction(db, sec.user_id, resume_id)


@resume_router.patch(
    "/{resume_id}/extracted-data",
    response_model=ResumeExtractionResponse,
    summary="Candidate corrections to extracted skills and text",
)
@resume_router.put(
    "/{resume_id}/skills",
    response_model=ResumeExtractionResponse,
    summary="Candidate corrections to extracted skills (PUT alias)",
)
@resume_router.put(
    "/me/{resume_id}/skills",
    response_model=ResumeExtractionResponse,
    summary="Candidate corrections to extracted skills (/me alias)",
)
async def update_extracted_data(
    resume_id: UUID,
    payload: ResumeExtractedDataUpdate,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ResumeExtractionResponse:
    return await candidate_service.update_extracted_data(db, sec.user_id, resume_id, payload)


@resume_router.post(
    "/{resume_id}/sync-profile",
    response_model=CandidateSkillsResponse,
    summary="Apply reviewed resume skills to candidate verified profile",
)
async def sync_resume_skills_to_profile(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateSkillsResponse:
    resume = await candidate_service.get_resume(db, sec.user_id, resume_id)
    return await candidate_service.update_skills(db, sec.user_id, resume.skills_extracted)


@resume_router.post(
    "/{resume_id}/set-default",
    response_model=CandidateResumeRead,
    summary="Designate active default resume for job applications",
)
@resume_router.put(
    "/{resume_id}/set-default",
    response_model=CandidateResumeRead,
    summary="Designate active default resume for job applications (PUT alias)",
)
@resume_router.put(
    "/me/{resume_id}/set-default",
    response_model=CandidateResumeRead,
    summary="Designate active default resume for job applications (/me alias)",
)
async def set_default_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> CandidateResumeRead:
    return await candidate_service.set_default_resume(db, sec.user_id, resume_id)


@resume_router.get(
    "/{resume_id}/download-url",
    response_model=ResumeDownloadUrlResponse,
    summary="Generate time-limited presigned S3 download URL",
)
@resume_router.get(
    "/{resume_id}/download",
    response_model=ResumeDownloadUrlResponse,
    summary="Generate time-limited presigned S3 download URL (alias)",
)
@resume_router.get(
    "/me/{resume_id}/download",
    response_model=ResumeDownloadUrlResponse,
    summary="Generate time-limited presigned S3 download URL (/me alias)",
)
async def get_resume_download_url(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> ResumeDownloadUrlResponse:
    return await candidate_service.get_download_url(db, sec.user_id, resume_id)


@resume_router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete candidate resume and remove object from storage",
)
@resume_router.delete(
    "/me/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete candidate resume and remove object from storage (/me alias)",
)
async def delete_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    sec: SecurityContext = Depends(require_authenticated_user),
) -> Response:
    await candidate_service.delete_resume(db, sec.user_id, resume_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
