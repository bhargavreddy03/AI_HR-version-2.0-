"""Aggregated API version 1 router."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount foundational system routers
api_v1_router.include_router(health_router)

# Future domain module routers (auth, organizations, jobs, etc.) will be mounted here in subsequent steps
