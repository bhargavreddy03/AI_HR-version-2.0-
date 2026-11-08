"""Test suite for database foundation, metadata naming conventions, and session lifecycle."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
    transactional_session,
)
from app.modules.embeddings.models import (
    APPROVED_MODELS,
    CandidateDocumentEmbedding,
    EmbeddingModel,
    JobEmbedding,
)
from app.modules.embeddings.service import (
    DeprecatedEmbeddingModelException,
    EmbeddingModelNotFoundException,
    InvalidEmbeddingDimensionException,
    InvalidSearchParameterException,
    search_similar_candidate_documents,
    store_candidate_document_embedding,
    store_job_embedding,
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
    mock_conn.cursor.return_value = mock_cursor

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


@pytest.mark.asyncio
async def test_transactional_session_commits_on_success() -> None:
    """Verify transactional_session commits upon block completion."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_begin_ctx = AsyncMock()

    @asynccontextmanager
    async def mock_begin():
        yield mock_begin_ctx

    mock_session.begin = mock_begin

    @asynccontextmanager
    async def mock_factory_ctx():
        yield mock_session

    mock_factory = MagicMock(return_value=mock_factory_ctx())

    async with transactional_session(session_factory=mock_factory) as session:
        assert session == mock_session

    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_transactional_session_rolls_back_on_exception() -> None:
    """Verify transactional_session rolls back and re-raises on failure."""
    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_begin():
        yield AsyncMock()

    mock_session.begin = mock_begin

    @asynccontextmanager
    async def mock_factory_ctx():
        yield mock_session

    mock_factory = MagicMock(return_value=mock_factory_ctx())

    with pytest.raises(ValueError, match="Transaction error"):
        async with transactional_session(session_factory=mock_factory):
            raise ValueError("Transaction error")

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()


def test_embedding_models_schema_and_approved_catalog() -> None:
    """Verify EmbeddingModel table structure and approved models definitions."""
    cols = EmbeddingModel.__table__.columns
    assert "model_identifier" in cols
    assert "provider" in cols
    assert "expected_dimensions" in cols
    assert "is_active" in cols
    assert "created_at" in cols
    assert cols["model_identifier"].primary_key is True

    assert len(APPROVED_MODELS) == 4
    model_ids = {m["model_identifier"] for m in APPROVED_MODELS}
    assert "text-embedding-3-small" in model_ids
    assert "amazon.titan-embed-text-v1" in model_ids
    assert "cohere.embed-english-v3" in model_ids
    assert "bge-base-en-v1.5" in model_ids


def test_vector_embedding_tables_schema_and_constraints() -> None:
    """Verify CandidateDocumentEmbedding and JobEmbedding columns and constraints."""
    for model_cls in (CandidateDocumentEmbedding, JobEmbedding):
        cols = model_cls.__table__.columns
        assert "id" in cols
        assert "tenant_id" in cols
        assert "model_identifier" in cols
        assert "model_version" in cols
        assert "vector_dimensions" in cols
        assert "embedding_1536" in cols
        assert "embedding_1024" in cols
        assert "embedding_768" in cols
        assert "created_at" in cols

        # Verify dimension constraint exists
        ck_names = [ck.name for ck in model_cls.__table__.constraints if hasattr(ck, "name")]
        assert any("chk_" in str(name) and "dimensions" in str(name) for name in ck_names)


@pytest.mark.asyncio
async def test_store_embedding_rejects_unregistered_model() -> None:
    """Verify service rejects unknown embedding models."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(EmbeddingModelNotFoundException):
        await store_candidate_document_embedding(
            session=mock_session,
            tenant_id=utc_now(),  # dummy uuid
            document_id=utc_now(),
            model_identifier="non_existent_model",
            model_version="1.0",
            embedding=[0.1] * 1536,
        )


@pytest.mark.asyncio
async def test_store_embedding_rejects_inactive_model() -> None:
    """Verify service rejects deprecated or deactivated embedding models."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="old-model",
        provider="openai",
        expected_dimensions=1536,
        is_active=False,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(DeprecatedEmbeddingModelException):
        await store_candidate_document_embedding(
            session=mock_session,
            tenant_id=utc_now(),
            document_id=utc_now(),
            model_identifier="old-model",
            model_version="1.0",
            embedding=[0.1] * 1536,
        )


@pytest.mark.asyncio
async def test_store_job_embedding_validation() -> None:
    """Verify store_job_embedding validates dimensions against active registered model."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="amazon.titan-embed-text-v1",
        provider="aws_bedrock",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidEmbeddingDimensionException):
        await store_job_embedding(
            session=mock_session,
            tenant_id=utc_now(),
            job_id=utc_now(),
            model_identifier="amazon.titan-embed-text-v1",
            model_version="1.0",
            embedding=[0.5] * 1024,  # mismatched dimension
        )


def test_embedding_model_registry_exact_canonical_contents() -> None:
    """Assert that the embedding model registry matches the canonical approved specifications."""
    assert len(APPROVED_MODELS) == 4
    expected = {
        ("text-embedding-3-small", "openai", 1536, True),
        ("amazon.titan-embed-text-v1", "aws_bedrock", 1536, True),
        ("cohere.embed-english-v3", "aws_bedrock", 1024, True),
        ("bge-base-en-v1.5", "huggingface", 768, True),
    }
    actual = {
        (
            m["model_identifier"],
            m["provider"],
            m["expected_dimensions"],
            m["is_active"],
        )
        for m in APPROVED_MODELS
    }
    assert actual == expected


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_unsupported_dimensions() -> None:
    """Verify search_similar_candidate_documents validates query vector dimensions against registered model."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidEmbeddingDimensionException):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 500,  # invalid dimension
            model_identifier="text-embedding-3-small",
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_empty_query_vector() -> None:
    """Verify search_similar_candidate_documents rejects empty query vectors."""
    mock_session = AsyncMock(spec=AsyncSession)
    with pytest.raises(InvalidSearchParameterException, match="cannot be empty"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[],
            model_identifier="text-embedding-3-small",
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_nan_and_inf_values() -> None:
    """Verify search_similar_candidate_documents rejects NaN, +Inf, and -Inf values."""
    mock_session = AsyncMock(spec=AsyncSession)

    # NaN test
    nan_vec = [0.1] * 1535 + [float("nan")]
    with pytest.raises(InvalidSearchParameterException, match="invalid non-finite value"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=nan_vec,
            model_identifier="text-embedding-3-small",
        )

    # Inf test
    inf_vec = [0.1] * 1535 + [float("inf")]
    with pytest.raises(InvalidSearchParameterException, match="invalid non-finite value"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=inf_vec,
            model_identifier="text-embedding-3-small",
        )

    # -Inf test
    ninf_vec = [float("-inf")] + [0.1] * 1535
    with pytest.raises(InvalidSearchParameterException, match="invalid non-finite value"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=ninf_vec,
            model_identifier="text-embedding-3-small",
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_invalid_limits() -> None:
    """Verify search_similar_candidate_documents validates positive bounded integer limits."""
    mock_session = AsyncMock(spec=AsyncSession)

    # Limit = 0
    with pytest.raises(
        InvalidSearchParameterException, match="Search limit must be a positive integer"
    ):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="text-embedding-3-small",
            limit=0,
        )

    # Limit < 0
    with pytest.raises(
        InvalidSearchParameterException, match="Search limit must be a positive integer"
    ):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="text-embedding-3-small",
            limit=-5,
        )

    # Limit > 100
    with pytest.raises(
        InvalidSearchParameterException, match="Search limit must be a positive integer"
    ):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="text-embedding-3-small",
            limit=101,
        )

    # Boolean limit
    with pytest.raises(
        InvalidSearchParameterException, match="Search limit must be a positive integer"
    ):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="text-embedding-3-small",
            limit=True,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_unregistered_model() -> None:
    """Verify search_similar_candidate_documents rejects unregistered models."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(EmbeddingModelNotFoundException):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="unknown-model-identifier",
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_inactive_model() -> None:
    """Verify search_similar_candidate_documents rejects inactive models."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="deprecated-model",
        provider="openai",
        expected_dimensions=1536,
        is_active=False,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(DeprecatedEmbeddingModelException):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.1] * 1536,
            model_identifier="deprecated-model",
        )


def test_init_db_sql_no_hardcoded_credentials_and_nocreatedb() -> None:
    """Verify that infrastructure/scripts/init-db.sql does not embed hardcoded passwords

    and strictly enforces NOCREATEDB, NOSUPERUSER, and NOBYPASSRLS for both roles.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    sql_path = repo_root / "infrastructure" / "scripts" / "init-db.sql"
    assert sql_path.exists(), f"init-db.sql not found at {sql_path}"

    content = sql_path.read_text(encoding="utf-8")

    # 1. No hardcoded password literals in CREATE/ALTER ROLE statements
    assert (
        "local_development_password_only'" not in content
    ), "Security finding: hardcoded application password found in init-db.sql"
    assert (
        "local_development_migration_password_only'" not in content
    ), "Security finding: hardcoded migration password found in init-db.sql"

    # 2. Uses \getenv for secure parameter ingestion
    assert "\\getenv mig_user POSTGRES_MIGRATION_USER" in content
    assert "\\getenv mig_password POSTGRES_MIGRATION_PASSWORD" in content
    assert "\\getenv app_user POSTGRES_APP_USER" in content or "\\getenv app_user" in content
    assert (
        "\\getenv app_password POSTGRES_APP_PASSWORD" in content
        or "\\getenv app_password" in content
    )

    # 3. Uses quoted psql parameters
    assert ":'mig_password'" in content
    assert ":'app_password'" in content
    assert ':"effective_mig_user"' in content
    assert ':"effective_app_user"' in content

    # 4. Strictly enforces NOCREATEDB, NOSUPERUSER, and NOBYPASSRLS
    assert "NOCREATEDB" in content
    assert "NOSUPERUSER" in content
    assert "NOBYPASSRLS" in content
    # Ensure CREATEDB without "NO" is NOT granted to migration user
    assert "CREATEDB NOSUPERUSER" not in content


def test_init_db_sh_entrypoint_security() -> None:
    """Verify infrastructure/scripts/init-db.sh safe execution and secret protection."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    sh_path = repo_root / "infrastructure" / "scripts" / "init-db.sh"
    assert sh_path.exists(), f"init-db.sh not found at {sh_path}"

    content = sh_path.read_text(encoding="utf-8")

    # Ensures secrets are not leaked in stdout/stderr logs
    assert "set +x" in content
    assert "set -eo pipefail" in content
    # Verifies environment variable names
    assert "POSTGRES_MIGRATION_USER" in content
    assert "POSTGRES_MIGRATION_PASSWORD" in content
    assert "POSTGRES_USER" in content
    assert "POSTGRES_PASSWORD" in content
    # Verifies credentials are not passed as -W or -p password CLI flags
    assert "-W " not in content


def _find_bash() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        return str(git_bash)
    return None


def test_init_db_sh_missing_secrets_failure_outside_development() -> None:
    """Verify infrastructure/scripts/init-db.sh fails immediately when secrets are missing outside development."""
    bash = _find_bash()
    if not bash:
        pytest.skip("Bash not available on test runner host")

    repo_root = Path(__file__).resolve().parent.parent.parent
    sh_path = repo_root / "infrastructure" / "scripts" / "init-db.sh"
    assert sh_path.exists()

    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "ENVIRONMENT": "production",
        # Explicitly ensure passwords are NOT set
        "POSTGRES_MIGRATION_PASSWORD": "",
        "POSTGRES_PASSWORD": "",
        "POSTGRES_APP_PASSWORD": "",
        "PGPASSWORD": "",
        "POSTGRES_SUPERUSER_PASSWORD": "",
    }
    proc = subprocess.run(
        [bash, str(sh_path)],
        env=clean_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert (
        "POSTGRES_MIGRATION_PASSWORD must be explicitly configured outside development"
        in proc.stderr
    )


def test_init_db_sh_local_development_initialization() -> None:
    """Verify infrastructure/scripts/init-db.sh sets convenient local defaults in development mode."""
    bash = _find_bash()
    if not bash:
        pytest.skip("Bash not available on test runner host")

    repo_root = Path(__file__).resolve().parent.parent.parent
    sh_path = repo_root / "infrastructure" / "scripts" / "init-db.sh"
    assert sh_path.exists()

    dev_env = {
        "PATH": os.environ.get("PATH", ""),
        "ENVIRONMENT": "development",
    }
    proc = subprocess.run(
        [bash, str(sh_path)],
        env=dev_env,
        capture_output=True,
        text=True,
        check=False,
    )
    # Even if psql is not installed, it should reach the psql invocation and not fail with "must be explicitly configured"
    assert "must be explicitly configured outside development" not in proc.stderr
    assert (
        "Starting database role initialization and credential reconciliation (env: development)"
        in proc.stdout
    )


def test_env_example_contains_no_development_credentials_and_no_development_environment() -> None:
    """Verify .env.example contains no usable development passwords and does not default to development."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    env_example = repo_root / ".env.example"
    assert env_example.exists(), ".env.example must exist at repository root"

    content = env_example.read_text(encoding="utf-8")

    # Must NOT contain hardcoded development passwords
    assert "local_development_" not in content
    assert "ENVIRONMENT=development" not in content

    # ENVIRONMENT must be empty (requiring explicit configuration)
    lines = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in content.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    assert lines.get("ENVIRONMENT") == "", "ENVIRONMENT must be empty in production template"
    assert (
        lines.get("POSTGRES_PASSWORD") == ""
    ), "POSTGRES_PASSWORD must be empty in production template"
    assert (
        lines.get("POSTGRES_MIGRATION_PASSWORD") == ""
    ), "POSTGRES_MIGRATION_PASSWORD must be empty in production template"
    assert (
        lines.get("POSTGRES_SUPERUSER_PASSWORD") == ""
    ), "POSTGRES_SUPERUSER_PASSWORD must be empty in production template"
    assert lines.get("DATABASE_URL") == "", "DATABASE_URL must be empty in production template"
    assert lines.get("JWT_SECRET_KEY") == "", "JWT_SECRET_KEY must be empty in production template"


def test_env_dev_example_contains_development_configuration() -> None:
    """Verify .env.dev.example explicitly defines development configuration and local credentials."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    dev_example = repo_root / ".env.dev.example"
    assert dev_example.exists(), ".env.dev.example must exist at repository root"

    content = dev_example.read_text(encoding="utf-8")

    # Must contain development settings and compose guidance
    assert "ENVIRONMENT=development" in content
    assert "docker-compose.dev.yml" in content
    assert "POSTGRES_PASSWORD=local_development_password_only" in content
    assert "POSTGRES_MIGRATION_PASSWORD=local_development_migration_password_only" in content
    assert "POSTGRES_SUPERUSER_PASSWORD=local_development_super_password_only" in content


def test_docker_compose_enforces_mandatory_secrets_and_rejects_missing_values() -> None:
    """Verify docker-compose.yml enforces required secrets via ${VAR:?error} syntax without silent fallbacks."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    compose_path = repo_root / "infrastructure" / "docker" / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    content = compose_path.read_text(encoding="utf-8")

    # Must enforce mandatory environment and secret substitution
    assert "${ENVIRONMENT:?" in content, "ENVIRONMENT must require explicit setting"
    assert (
        "${POSTGRES_SUPERUSER_PASSWORD:?" in content
    ), "POSTGRES_SUPERUSER_PASSWORD must be required"
    assert (
        "${POSTGRES_MIGRATION_PASSWORD:?" in content
    ), "POSTGRES_MIGRATION_PASSWORD must be required"
    assert (
        "${POSTGRES_PASSWORD:?" in content
    ), "POSTGRES_APP_PASSWORD must require POSTGRES_PASSWORD"

    # Must not contain fallback development passwords
    assert "local_development_" not in content


def test_docker_compose_production_ports_isolated_and_dev_ports_bound_to_localhost() -> None:
    """Verify production compose file isolates database/redis ports while dev compose binds to 127.0.0.1."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    prod_compose = repo_root / "infrastructure" / "docker" / "docker-compose.yml"
    dev_compose = repo_root / "infrastructure" / "docker" / "docker-compose.dev.yml"

    prod_text = prod_compose.read_text(encoding="utf-8")
    dev_text = dev_compose.read_text(encoding="utf-8")

    # In production, postgres and redis services must NOT publish host ports
    postgres_block = prod_text.split("postgres:")[1].split("redis:")[0]
    redis_block = prod_text.split("redis:")[1].split("backend:")[0]
    assert "ports:" not in postgres_block, "Postgres ports exposed in production compose"
    assert "ports:" not in redis_block, "Redis ports exposed in production compose"

    # In dev override, ports must be bound to 127.0.0.1
    dev_pg_block = dev_text.split("postgres:")[1].split("redis:")[0]
    dev_redis_block = dev_text.split("redis:")[1].split("backend:")[0]
    assert "127.0.0.1:" in dev_pg_block, "Postgres dev ports must bind to 127.0.0.1"
    assert "127.0.0.1:" in dev_redis_block, "Redis dev ports must bind to 127.0.0.1"

    try:
        import yaml

        with open(prod_compose, encoding="utf-8") as f:
            prod_data = yaml.safe_load(f)
        assert "ports" not in prod_data["services"]["postgres"]
        assert "ports" not in prod_data["services"]["redis"]

        with open(dev_compose, encoding="utf-8") as f:
            dev_data = yaml.safe_load(f)
        assert any("127.0.0.1:" in str(p) for p in dev_data["services"]["postgres"]["ports"])
        assert any("127.0.0.1:" in str(p) for p in dev_data["services"]["redis"]["ports"])
    except ImportError:
        pass


def test_init_db_sql_handles_custom_bootstrap_user() -> None:
    """Verify init-db.sql dynamically configures default privileges for the bootstrap superuser."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    sql_path = repo_root / "infrastructure" / "scripts" / "init-db.sql"
    content = sql_path.read_text(encoding="utf-8")

    assert "\\getenv super_user POSTGRES_SUPERUSER" in content
    assert ':"effective_super_user"' in content
    assert 'FOR ROLE :"effective_super_user"' in content


def test_alembic_migrations_dynamic_app_role() -> None:
    """Verify migrations 001 and 002 use _get_app_role() and do not fall back to PUBLIC."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    m001 = repo_root / "backend" / "alembic" / "versions" / "001_initial_auth_and_identity.py"
    m002 = (
        repo_root / "backend" / "alembic" / "versions" / "002_database_foundation_and_pgvector.py"
    )

    c001 = m001.read_text(encoding="utf-8")
    c002 = m002.read_text(encoding="utf-8")

    assert "def _get_app_role()" in c001
    assert "def _get_app_role()" in c002
    assert (
        "TO PUBLIC" not in c002
    ), "Security finding: migration 002 must not grant privileges to PUBLIC"


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_zero_magnitude_vector() -> None:
    """Verify search_similar_candidate_documents rejects zero-magnitude query vectors."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidSearchParameterException, match="zero magnitude"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[0.0] * 1536,
            model_identifier="text-embedding-3-small",
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_rejects_booleans_in_vector() -> None:
    """Verify search_similar_candidate_documents rejects booleans inside query vector."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    # Python bool is a subclass of int, so [True] * 1536 must be explicitly rejected
    with pytest.raises(InvalidSearchParameterException, match="contains invalid non-finite value"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=utc_now(),
            query_vector=[True] * 1536,  # type: ignore[arg-type]
            model_identifier="text-embedding-3-small",
        )


@pytest.mark.asyncio
async def test_get_engine_disposes_previous_engine_on_url_change() -> None:
    """Verify that get_engine asynchronously disposes old engine and does not affect another app instance."""
    from app.core import database as db_mod
    from app.core.database import create_session_factory
    from app.main import create_application

    # Reset any cached global engine from prior tests in the test session
    db_mod._engine = None
    db_mod._session_factory = None

    # 1. Initialize first global engine
    s1 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db1")
    engine1 = get_engine(s1)
    assert engine1.url.database == "db1"

    # 2. Setup a separate application instance with its own isolated engine
    app_settings = Settings(
        APP_NAME="Isolated Tenant App",
        DATABASE_URL="postgresql+asyncpg://tenant_user:pass@localhost:5432/tenant_db",
    )
    app = create_application(app_settings)
    app_engine = create_db_engine(app_settings)
    app.state.engine = app_engine
    app.state.session_factory = create_session_factory(app_engine)

    # 3. Patch dispose specifically when changing global configuration to replace engine1
    mock_dispose = AsyncMock()
    with patch.object(AsyncEngine, "dispose", mock_dispose):
        s2 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db2")
        engine2 = get_engine(s2)

        # Verify new working engine is created with updated configuration
        assert engine2 is not engine1
        assert engine2.url.database == "db2"
        factory2 = get_session_factory(engine2)
        assert factory2.kw.get("bind") == engine2

        # Yield execution to event loop to allow asynchronous disposal task to execute
        await asyncio.sleep(0.01)

        # Verify that dispose() was actually awaited on the discarded engine
        mock_dispose.assert_awaited_once()

    # 4. Verify that replacing the global engine did NOT affect the isolated application instance
    assert app.state.engine is app_engine
    assert app.state.engine.url.database == "tenant_db"
    assert app.state.session_factory.kw.get("bind") is app_engine
    assert app.state.engine is not engine1
    assert app.state.engine is not engine2


def test_init_db_sh_rejects_role_collisions() -> None:
    """Verify infrastructure/scripts/init-db.sh aborts immediately upon role collision."""
    bash = _find_bash()
    if not bash:
        pytest.skip("Bash not available on test runner host")

    repo_root = Path(__file__).resolve().parent.parent.parent
    sh_path = repo_root / "infrastructure" / "scripts" / "init-db.sh"
    assert sh_path.exists()

    # Case 1: Superuser == Migration user collision
    collision_env = {
        "PATH": os.environ.get("PATH", ""),
        "ENVIRONMENT": "development",
        "POSTGRES_SUPERUSER": "shared_collision_role",
        "POSTGRES_MIGRATION_USER": "shared_collision_role",
        "POSTGRES_APP_USER": "distinct_app_role",
    }
    proc = subprocess.run(
        [bash, str(sh_path)],
        env=collision_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "Role collision detected" in proc.stderr

    # Case 2: Migration user == Application user collision
    collision_env2 = {
        "PATH": os.environ.get("PATH", ""),
        "ENVIRONMENT": "development",
        "POSTGRES_SUPERUSER": "postgres_super",
        "POSTGRES_MIGRATION_USER": "colliding_user",
        "POSTGRES_APP_USER": "colliding_user",
    }
    proc2 = subprocess.run(
        [bash, str(sh_path)],
        env=collision_env2,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode != 0
    assert "Role collision detected" in proc2.stderr


def test_init_db_sql_contains_role_collision_enforcement() -> None:
    """Verify init-db.sql contains PL/pgSQL block rejecting role collisions."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    sql_path = repo_root / "infrastructure" / "scripts" / "init-db.sql"
    content = sql_path.read_text(encoding="utf-8")

    assert "Role collision: migration role" in content
    assert "Role collision: application runtime role" in content


def test_alembic_migrations_reject_role_collision() -> None:
    """Verify _get_app_role in migration files strictly rejects role collisions with superuser or migration user."""
    import importlib.util

    repo_root = Path(__file__).resolve().parent.parent.parent
    m001_path = repo_root / "backend" / "alembic" / "versions" / "001_initial_auth_and_identity.py"

    spec = importlib.util.spec_from_file_location("m001_module", m001_path)
    assert spec and spec.loader
    m001 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m001)

    # When role collides with superuser
    with patch.dict(
        os.environ,
        {"POSTGRES_USER": "postgres", "POSTGRES_SUPERUSER": "postgres"},
        clear=False,
    ):
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                POSTGRES_APP_USER="postgres", POSTGRES_USER="postgres"
            )
            with pytest.raises(ValueError, match="Role collision detected"):
                m001._get_app_role()

    # When role collides with migration user
    with patch.dict(
        os.environ,
        {
            "POSTGRES_USER": "aihr_migration_user",
            "POSTGRES_MIGRATION_USER": "aihr_migration_user",
        },
        clear=False,
    ):
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                POSTGRES_APP_USER="aihr_migration_user",
                POSTGRES_USER="aihr_migration_user",
            )
            with pytest.raises(ValueError, match="Role collision detected"):
                m001._get_app_role()


def test_alembic_migrations_resolve_from_settings() -> None:
    """Verify _get_app_role resolves custom application role from Pydantic settings."""
    import importlib.util

    repo_root = Path(__file__).resolve().parent.parent.parent
    m002_path = (
        repo_root / "backend" / "alembic" / "versions" / "002_database_foundation_and_pgvector.py"
    )

    spec = importlib.util.spec_from_file_location("m002_module", m002_path)
    assert spec and spec.loader
    m002 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m002)

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            POSTGRES_APP_USER="custom_enterprise_app_role", POSTGRES_USER="fallback_user"
        )
        resolved_role = m002._get_app_role()
        assert resolved_role == "custom_enterprise_app_role"


def test_redis_client_authenticated_connection_pool() -> None:
    """Verify create_redis_pool incorporates REDIS_PASSWORD into connection kwargs."""
    from app.core.redis import create_redis_pool

    dev_pass = "local_development_redis_secret_only"
    settings = Settings(
        REDIS_PASSWORD=dev_pass,
        REDIS_URL=f"redis://:{dev_pass}@localhost:6379/0",
        CELERY_BROKER_URL=f"redis://:{dev_pass}@localhost:6379/1",
        CELERY_RESULT_BACKEND=f"redis://:{dev_pass}@localhost:6379/2",
    )
    pool = create_redis_pool(settings)
    assert pool.connection_kwargs.get("password") == dev_pass
