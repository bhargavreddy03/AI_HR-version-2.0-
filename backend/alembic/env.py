"""Alembic environment configuration for asynchronous SQLAlchemy 2.x migrations."""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ensure backend root is in sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import app.modules.auth.models  # noqa: F401, E402
import app.modules.embeddings.models  # noqa: F401, E402
import app.modules.organizations.models  # noqa: F401, E402
from app.core.base import Base  # noqa: E402
from app.core.config import get_settings  # noqa: E402

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

# Set declarative metadata for autogenerate support
target_metadata = Base.metadata

# Inject active database URL from config or Pydantic Settings fallback
active_url = config.get_main_option("sqlalchemy.url")
settings = get_settings()
migration_url = (
    getattr(settings, "DATABASE_MIGRATION_URL", None)
    or getattr(settings, "DATABASE_SYNC_URL", None)
    or settings.DATABASE_URL
)

# Prioritize dynamic environment/settings URL when alembic.ini has empty or localhost URL
if not active_url or (
    migration_url and migration_url != active_url and "localhost" in (active_url or "")
):
    config.set_main_option("sqlalchemy.url", migration_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without an active DB engine connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run actual migrations in an isolated sync connection context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an AsyncEngine and associate a connection with the context."""
    configuration = config.get_section(config.config_ini_section, {})
    url = config.get_main_option("sqlalchemy.url")
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
