"""System health, liveness, and dependency readiness probe endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings, get_settings
from app.core.database import check_database_health
from app.core.redis import check_redis_health

router = APIRouter(prefix="/health", tags=["System Health"])


def get_app_settings(request: Request) -> Settings:
    """Retrieve Settings instance configured on the application state with fallback."""
    app_settings = getattr(request.app.state, "settings", None)
    if isinstance(app_settings, Settings):
        return app_settings
    return get_settings()


@router.get(
    "",
    summary="Service Liveness Probe",
    description="Verify that the FastAPI application process is active and accepting requests.",
    status_code=status.HTTP_200_OK,
)
async def liveness_check(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, Any]:
    """Return process liveness state and basic metadata."""
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
async def readiness_check(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, Any]:
    """Verify live connectivity against configured dependencies without placeholder claims."""
    engine = getattr(request.app.state, "engine", None)
    redis_client = getattr(request.app.state, "redis_client", None)

    # Execute concurrent live health probes against PostgreSQL and Redis using instance clients
    db_healthy, redis_healthy = await asyncio.gather(
        check_database_health(engine=engine, settings=settings),
        check_redis_health(client=redis_client, settings=settings),
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
