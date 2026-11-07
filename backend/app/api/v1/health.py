"""System health, liveness, and dependency readiness probe endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.core.database import check_database_health
from app.core.redis import check_redis_health

router = APIRouter(prefix="/health", tags=["System Health"])


@router.get(
    "",
    summary="Service Liveness Probe",
    description="Verify that the FastAPI application process is active and accepting requests.",
    status_code=status.HTTP_200_OK,
)
async def liveness_check() -> dict[str, Any]:
    """Return process liveness state and basic metadata."""
    settings = get_settings()
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
    }


@router.get(
    "/ready",
    summary="Service Readiness Probe",
    description="Verify that required downstream dependencies (PostgreSQL, Redis) are healthy and reachable.",
    status_code=status.HTTP_200_OK,
)
async def readiness_check(response: Response) -> dict[str, Any]:
    """Verify live connectivity against configured dependencies without placeholder claims."""
    settings = get_settings()

    # Execute concurrent live health probes against PostgreSQL and Redis
    db_healthy, redis_healthy = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        return_exceptions=False,
    )

    dependencies = {
        "database": "connected" if db_healthy else "unavailable",
        "redis": "connected" if redis_healthy else "unavailable",
    }

    all_ready = db_healthy and redis_healthy

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "environment": settings.ENVIRONMENT,
            "version": settings.APP_VERSION,
            "dependencies": dependencies,
            "message": "One or more critical dependencies are unreachable.",
        }

    return {
        "status": "ready",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
        "dependencies": dependencies,
    }
