"""Test suite for database foundation, metadata naming conventions, and session lifecycle."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.config import Config
from app.core.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TenantScopedMixin,
    TimestampMixin,
)
from app.core.config import Settings
from app.core.database import (
    check_database_health,
    get_db,
    get_engine,
    get_session_factory,
)


class DummyModel(Base, TimestampMixin, TenantScopedMixin):
    """Dummy entity to test declarative base and naming conventions."""

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


def test_alembic_config_validation() -> None:
    """Verify that alembic.ini parses correctly and references the alembic directory."""
    alembic_cfg = Config("alembic.ini")
    assert alembic_cfg.get_main_option("script_location") == "alembic"
    assert alembic_cfg.get_main_option("output_encoding") == "utf-8"
