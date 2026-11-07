"""FastAPI application factory, lifespan management, and middleware initialization.

Follows the Modular Monolith architecture approved in Step 2.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import Settings, get_settings
from app.core.database import (
    create_db_engine,
    create_session_factory,
    dispose_app_database,
)
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import CorrelationIdMiddleware
from app.core.redis import (
    create_redis_client,
    dispose_app_redis,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager coordinating startup and shutdown events."""
    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    setup_logging(settings)

    # Initialize connection pools on startup for non-testing environments if not pre-injected
    if settings.ENVIRONMENT != "testing":
        if getattr(app.state, "engine", None) is None:
            engine = create_db_engine(settings)
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)
        if getattr(app.state, "redis_client", None) is None:
            app.state.redis_client = create_redis_client(settings)

    yield

    # Clean instance-scoped shutdown: dispose ONLY this application's resources
    await dispose_app_database(app)
    await dispose_app_redis(app)


def create_application(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure the FastAPI modular monolith application."""
    app_settings = settings if settings is not None else get_settings()

    # Configure structured logging for the application instance
    setup_logging(app_settings)

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

    # 1. Register Request Correlation ID Middleware (outermost for accurate logging)
    app.add_middleware(CorrelationIdMiddleware, settings=app_settings)

    # 2. Configure CORS Middleware with explicit environment origins
    if app_settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in app_settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    # 3. Register Centralized RFC 7807 Exception Handlers
    register_exception_handlers(app)

    # 4. Mount Versioned API Structure under /api/v1
    app.include_router(api_v1_router)

    return app


app = create_application()
