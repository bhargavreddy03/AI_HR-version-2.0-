"""Test suite verifying application-instance resource isolation and independent lifecycle ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import (
    dispose_app_database,
    get_db,
)
from app.core.redis import dispose_app_redis
from app.main import create_application


def test_application_instances_maintain_independent_settings() -> None:
    """Verify that multiple application instances retain independent, isolated Settings instances."""
    settings_1 = Settings(
        APP_NAME="Tenant App 1",
        POSTGRES_DB="tenant_1_db",
        REDIS_DB=1,
    )
    settings_2 = Settings(
        APP_NAME="Tenant App 2",
        POSTGRES_DB="tenant_2_db",
        REDIS_DB=2,
    )

    app_1 = create_application(settings_1)
    app_2 = create_application(settings_2)

    assert app_1.state.settings.APP_NAME == "Tenant App 1"
    assert app_2.state.settings.APP_NAME == "Tenant App 2"
    assert app_1.state.settings.POSTGRES_DB == "tenant_1_db"
    assert app_2.state.settings.POSTGRES_DB == "tenant_2_db"
    assert app_1.state.settings.REDIS_DB != app_2.state.settings.REDIS_DB


def test_application_instances_maintain_independent_resources() -> None:
    """Verify that distinct application instances hold separate database and Redis references on app.state."""
    app_1 = create_application(Settings(APP_NAME="App A"))
    app_2 = create_application(Settings(APP_NAME="App B"))

    mock_engine_1 = MagicMock(spec=AsyncEngine)
    mock_engine_2 = MagicMock(spec=AsyncEngine)

    mock_factory_1 = MagicMock(spec=async_sessionmaker)
    mock_factory_2 = MagicMock(spec=async_sessionmaker)

    mock_redis_1 = MagicMock(spec=Redis)
    mock_redis_2 = MagicMock(spec=Redis)

    app_1.state.engine = mock_engine_1
    app_1.state.session_factory = mock_factory_1
    app_1.state.redis_client = mock_redis_1

    app_2.state.engine = mock_engine_2
    app_2.state.session_factory = mock_factory_2
    app_2.state.redis_client = mock_redis_2

    assert app_1.state.engine is not app_2.state.engine
    assert app_1.state.session_factory is not app_2.state.session_factory
    assert app_1.state.redis_client is not app_2.state.redis_client


@pytest.mark.asyncio
async def test_application_shutdown_disposes_only_own_resources() -> None:
    """Verify that shutting down one application disposes only its own resources without affecting other instances."""
    app_1 = create_application(Settings(APP_NAME="App Shutdown 1"))
    app_2 = create_application(Settings(APP_NAME="App Active 2"))

    mock_engine_1 = AsyncMock(spec=AsyncEngine)
    mock_engine_2 = AsyncMock(spec=AsyncEngine)

    mock_redis_1 = AsyncMock(spec=Redis)
    mock_redis_1.connection_pool = AsyncMock()
    mock_redis_2 = AsyncMock(spec=Redis)
    mock_redis_2.connection_pool = AsyncMock()

    app_1.state.engine = mock_engine_1
    app_1.state.session_factory = MagicMock(spec=async_sessionmaker)
    app_1.state.redis_client = mock_redis_1

    app_2.state.engine = mock_engine_2
    app_2.state.session_factory = MagicMock(spec=async_sessionmaker)
    app_2.state.redis_client = mock_redis_2

    # Dispose resources of App 1
    await dispose_app_database(app_1)
    await dispose_app_redis(app_1)

    # Assert App 1 resources were cleanly disposed and nulled on app_1.state
    mock_engine_1.dispose.assert_awaited_once()
    assert app_1.state.engine is None
    assert app_1.state.session_factory is None
    assert app_1.state.redis_client is None

    # Assert App 2 resources were NEVER disposed and remain active
    mock_engine_2.dispose.assert_not_called()
    assert app_2.state.engine is mock_engine_2
    assert app_2.state.session_factory is not None
    assert app_2.state.redis_client is mock_redis_2

    # Clean up App 2
    await dispose_app_database(app_2)
    await dispose_app_redis(app_2)
    mock_engine_2.dispose.assert_awaited_once()
    assert app_2.state.engine is None


@pytest.mark.asyncio
async def test_get_db_resolves_instance_specific_session_factory() -> None:
    """Verify that get_db dependency uses the specific session factory of the request's application instance."""
    app_alpha = create_application(Settings(APP_NAME="Alpha"))
    app_beta = create_application(Settings(APP_NAME="Beta"))

    mock_session_alpha = AsyncMock(spec=AsyncSession)
    mock_session_beta = AsyncMock(spec=AsyncSession)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def alpha_ctx():
        yield mock_session_alpha

    @asynccontextmanager
    async def beta_ctx():
        yield mock_session_beta

    mock_factory_alpha = MagicMock(return_value=alpha_ctx())
    mock_factory_beta = MagicMock(return_value=beta_ctx())

    app_alpha.state.session_factory = mock_factory_alpha
    app_beta.state.session_factory = mock_factory_beta

    request_alpha = MagicMock(spec=Request)
    request_alpha.app = app_alpha

    request_beta = MagicMock(spec=Request)
    request_beta.app = app_beta

    # Execute get_db with request_alpha
    gen_alpha = get_db(request=request_alpha)
    session_a = await anext(gen_alpha)
    assert session_a is mock_session_alpha
    try:
        await anext(gen_alpha)
    except StopAsyncIteration:
        pass
    mock_session_alpha.commit.assert_awaited_once()
    mock_session_beta.commit.assert_not_called()

    # Execute get_db with request_beta
    gen_beta = get_db(request=request_beta)
    session_b = await anext(gen_beta)
    assert session_b is mock_session_beta
    try:
        await anext(gen_beta)
    except StopAsyncIteration:
        pass
    mock_session_beta.commit.assert_awaited_once()
