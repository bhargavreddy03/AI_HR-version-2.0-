"""Aggregated API version 1 router."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.tasks import router as tasks_router
from app.modules.auth.router import router as auth_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount foundational system routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(tasks_router)

# Mount identity & authentication domain router (Step 3.3)
api_v1_router.include_router(auth_router)
