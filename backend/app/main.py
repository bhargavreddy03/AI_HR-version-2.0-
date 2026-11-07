"""FastAPI application factory and lifecycle entry point.

Follows the Modular Monolith architecture approved in Step 2.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    setup_logging()
    # Startup: Database engine and Redis connection pool verification will be initialized in Step 3.2+
    yield
    # Shutdown: Clean teardown of connection pools


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI modular monolith application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # Configure CORS Middleware
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # System Health & Liveness Probes
    @app.get(
        "/api/v1/health",
        tags=["System"],
        summary="Service Liveness Probe",
        status_code=status.HTTP_200_OK,
    )
    async def liveness_check() -> Dict[str, str]:
        """Verify that the FastAPI service process is active and accepting requests."""
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "version": settings.APP_VERSION,
        }

    @app.get(
        "/api/v1/health/ready",
        tags=["System"],
        summary="Service Readiness Probe",
        status_code=status.HTTP_200_OK,
    )
    async def readiness_check() -> Dict[str, str]:
        """Verify that downstream dependencies (Database, Redis) are ready."""
        # Detailed connectivity probes will be wired to SQLAlchemy and Redis in Step 3.2
        return {
            "status": "ready",
            "database": "uninitialized",
            "redis": "uninitialized",
        }

    return app


app = create_application()
