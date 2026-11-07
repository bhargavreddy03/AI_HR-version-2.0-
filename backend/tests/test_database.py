"""Test suite for database foundation, metadata naming conventions, and session lifecycle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.config import Config
from app.core.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TenantScopedMixin,
    TimestampMixin,
    utc_now,
)
from app.core.config import Settings
from app.core.database import (
    check_database_health,
    create_db_engine,
    get_db,
    get_engine,
    get_session_factory,
)


class DummyModel(Base, TimestampMixin, TenantScopedMixin):
    """Dummy entity to test declarative base, timestamps, and naming conventions."""

    __tablename__ = "dummy_test_entities"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)


def test_metadata_naming_conventions() -> None:
    """Verify that SQLAlchemy metadata enforces canonical PostgreSQL naming conventions."""
    assert Base.metadata.naming_convention == POSTGRES_NAMING_CONVENTION
    assert POSTGRES_NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert (
        POSTGRES_NAMING_CONVENTION["fk"]
        == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )
    assert POSTGRES_NAMING_CONVENTION["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert POSTGRES_NAMING_CONVENTION["ix"] == "ix_%(column_0_label)s"


def test_base_mixins_columns() -> None:
    """Verify that TimestampMixin and TenantScopedMixin inject proper attributes."""
    columns = DummyModel.__table__.columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert "tenant_id" in columns
    assert columns["tenant_id"].nullable is False


def test_timezone_aware_timestamp_handling() -> None:
    """Verify that TimestampMixin uses timezone-aware UTC datetimes and rejects naive timestamps."""
    current_time = utc_now()
    assert current_time.tzinfo is not None
    assert current_time.tzinfo == UTC
    assert current_time.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    # Verify column definitions enforce TIMESTAMPTZ and timezone-aware default callable
    created_col = DummyModel.__table__.c.created_at
    updated_col = DummyModel.__table__.c.updated_at
    assert created_col.type.timezone is True
    assert updated_col.type.timezone is True
    assert created_col.default is not None
    assert callable(created_col.default.arg)
    assert updated_col.onupdate is not None
    assert callable(updated_col.onupdate.arg)

    # Verify generated values are timezone-aware UTC
    generated_created = created_col.default.arg(None)
    assert generated_created.tzinfo == UTC
    generated_updated = updated_col.onupdate.arg(None)
    assert generated_updated.tzinfo == UTC


def test_get_engine_and_factory(test_settings: Settings) -> None:
    """Verify AsyncEngine and async_sessionmaker instantiation."""
    engine = get_engine(settings=test_settings)
    assert engine is not None
    factory = get_session_factory(engine=engine, settings=test_settings)
    assert factory is not None


@pytest.mark.asyncio
async def test_get_db_session_lifecycle_commit() -> None:
    """Verify that get_db commits on successful execution."""
    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_factory = MagicMock(return_value=mock_session_ctx())

    with patch("app.core.database.get_session_factory", return_value=mock_factory):
        async_gen = get_db()
        session = await anext(async_gen)
        assert session == mock_session
        try:
            await anext(async_gen)
        except StopAsyncIteration:
            pass

        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_session_lifecycle_rollback_on_error() -> None:
    """Verify that get_db rolls back when an exception occurs inside the session block."""
    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_factory = MagicMock(return_value=mock_session_ctx())

    with patch("app.core.database.get_session_factory", return_value=mock_factory):
        async_gen = get_db()
        session = await anext(async_gen)
        assert session == mock_session

        with pytest.raises(RuntimeError):
            await async_gen.athrow(RuntimeError("Simulated database failure"))

        mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_uses_request_app_state_session_factory() -> None:
    """Verify that get_db utilizes application-state session factory when request is supplied."""
    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_factory = MagicMock(return_value=mock_session_ctx())

    mock_request = MagicMock(spec=Request)
    mock_request.app.state.session_factory = mock_factory

    async_gen = get_db(request=mock_request)
    session = await anext(async_gen)
    assert session == mock_session
    try:
        await anext(async_gen)
    except StopAsyncIteration:
        pass

    mock_factory.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_database_health_success() -> None:
    """Verify that check_database_health returns True on successful query."""
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_conn.execute.return_value = mock_result

    @asynccontextmanager
    async def mock_connect_ctx():
        yield mock_conn

    mock_engine.connect = MagicMock(return_value=mock_connect_ctx())

    result = await check_database_health(engine=mock_engine)
    assert result is True


@pytest.mark.asyncio
async def test_check_database_health_failure() -> None:
    """Verify that check_database_health returns False when connection fails."""
    mock_engine = MagicMock()

    @asynccontextmanager
    async def mock_connect_ctx():
        raise TimeoutError("DB connection timed out")
        yield  # type: ignore[unreachable]

    mock_engine.connect = MagicMock(return_value=mock_connect_ctx())

    result = await check_database_health(engine=mock_engine)
    assert result is False


def test_pool_checkin_listener_failure_invalidates_connection(test_settings: Settings) -> None:
    """Verify that pool checkin failure invalidates connection record and raises without swallowing."""
    engine = create_db_engine(test_settings)
    # Simulate postgresql dialect
    engine.dialect.name = "postgresql"

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = RuntimeError("Connection dropped during reset")
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_record = MagicMock()

    # Dispatch checkin event directly through pool listeners
    with pytest.raises(RuntimeError, match="Connection dropped during reset"):
        engine.sync_engine.pool.dispatch.checkin(mock_conn, mock_record)

    # Confirm connection was explicitly invalidated
    mock_record.invalidate.assert_called_once()


def test_alembic_config_validation() -> None:
    """Verify that alembic.ini parses correctly and references the alembic directory."""
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    assert "alembic" in str(alembic_cfg.get_main_option("script_location"))
    assert alembic_cfg.get_main_option("output_encoding") == "utf-8"
