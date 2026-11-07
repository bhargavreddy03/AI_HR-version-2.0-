"""FastAPI application factory and lifecycle entry point.

Follows the Modular Monolith architecture approved in Step 2.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    setup_logging()
    # Startup: Database engine and Redis connection pool verification will be initialized in Step 3.2+
    yield
    # Shutdown: Clean teardown of connection pools


def create_application(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure the FastAPI modular monolith application."""
    app_settings = settings if settings is not None else get_settings()

    app = FastAPI(
        title=app_settings.APP_NAME,
        version=app_settings.APP_VERSION,
        debug=app_settings.DEBUG,
        docs_url="/docs" if app_settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if app_settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if app_settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # Attach settings to application state
    app.state.settings = app_settings

    # Configure CORS Middleware
    if app_settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in app_settings.BACKEND_CORS_ORIGINS],
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
    async def liveness_check() -> dict[str, Any]:
        """Verify that the FastAPI service process is active and accepting requests."""
        return {
            "status": "healthy",
            "environment": app_settings.ENVIRONMENT,
            "version": app_settings.APP_VERSION,
        }

    @app.get(
        "/api/v1/health/ready",
        tags=["System"],
        summary="Service Readiness Probe",
        status_code=status.HTTP_200_OK,
    )
    async def readiness_check() -> dict[str, Any]:
        """Placeholder readiness probe distinguishing process readiness from infrastructure dependencies.

        Real database and Redis connectivity probes will be implemented in Step 3.2.
        Until Step 3.2 is reached, downstream dependencies are explicitly flagged as unverified/pending.
        """
        return {
            "status": "not_ready",
            "stage": "step_3_1_foundation",
            "dependencies": {
                "database": "pending_step_3_2_initialization",
                "redis": "pending_step_3_2_initialization",
            },
            "message": "Service foundation online; downstream dependency health checks will be enabled in Step 3.2.",
        }

    return app


app = create_application()
