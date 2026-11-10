"""Aggregated API version 1 router."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.tasks import router as tasks_router
from app.modules.auth.router import router as auth_router
from app.modules.candidates.router import candidate_router, resume_router
from app.modules.documents.router import router as documents_router
from app.modules.jobs.router import job_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount foundational system routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(tasks_router)

# Mount identity & authentication domain router (Step 3.3)
api_v1_router.include_router(auth_router)

# Mount documents & secure ingestion domain router (Step 3.10)
api_v1_router.include_router(documents_router)

# Mount candidate portal & resume domain routers (Step 4.1)
api_v1_router.include_router(candidate_router)
api_v1_router.include_router(resume_router)

# Mount job discovery & application domain router (Step 4.1)
api_v1_router.include_router(job_router)
