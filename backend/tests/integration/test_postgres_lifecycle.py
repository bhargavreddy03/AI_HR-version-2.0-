"""Integration test suite verifying PostgreSQL 16 connection lifecycle, RLS isolation, migrations, and concurrency controls."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.base import generate_uuid7, utc_now
from app.core.config import Settings
from app.core.database import (
    create_db_engine,
    create_session_factory,
    register_pool_cleanup_listener,
)
from app.core.errors import AuthenticationException
from app.core.security import hash_password, set_tenant_context
from app.modules.auth.crypto import (
    encrypt_mfa_secret,
    generate_backup_codes,
    generate_secure_token,
    generate_totp_secret,
    hash_backup_code,
    hash_token,
    verify_backup_code,
)
from app.modules.auth.models import (
    User,
    UserSession,
)
from app.modules.auth.service import refresh_session_tokens, verify_mfa_challenge
from app.modules.organizations.models import (
    Organization,
    OrganizationMembership,
    Role,
)

# Read test database URLs from environment or standard defaults
INTEGRATION_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aihr_app_user:test_password_only@localhost:5432/ai_hr_db_test",
)


async def is_postgres_reachable() -> bool:
    """Check if PostgreSQL service is reachable within 2 seconds."""
    try:
        engine = create_async_engine(INTEGRATION_DB_URL, pool_pre_ping=True)
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT 1"))
                return res.scalar() == 1
    except Exception:
        return False
    finally:
        try:
            await engine.dispose()
        except Exception:
            pass


def postgres_is_live() -> bool:
    """Synchronous probe wrapper for pytest skip condition."""
    try:
        return asyncio.run(is_postgres_reachable())
    except Exception:
        return False


# Determine reachability once for test session skipping
POSTGRES_AVAILABLE = postgres_is_live()

skip_if_no_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason=f"PostgreSQL 16 service is unavailable at {INTEGRATION_DB_URL}",
)


@pytest.fixture(scope="module")
def integration_settings() -> Settings:
    """Provide settings for PostgreSQL integration testing."""
    return Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        POSTGRES_PASSWORD="test_password_only",
        DATABASE_URL=INTEGRATION_DB_URL,
        DATABASE_SYNC_URL=INTEGRATION_DB_URL.replace("+asyncpg", ""),
        MFA_ENCRYPTION_KEY="integration_test_mfa_encryption_key_at_least_32_bytes_long",
    )


@pytest.fixture(scope="module", autouse=True)
def ensure_database_schema(integration_settings: Settings) -> None:
    """Ensure latest Alembic migrations are applied before running integration tests."""
    if not POSTGRES_AVAILABLE:
        return
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", integration_settings.DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_connection_and_session_lifecycle(
    integration_settings: Settings,
) -> None:
    """Verify live database connectivity, session creation, query execution, and clean teardown."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            result = await session.execute(text("SELECT 1 AS probe"))
            val = result.scalar()
            assert val == 1
            await session.commit()
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_commit_and_rollback_behavior(
    integration_settings: Settings,
) -> None:
    """Verify transaction commit and rollback mechanics against PostgreSQL."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    try:
        # Step 1: Create a temporary table and commit row A
        async with session_factory() as session:
            await session.execute(
                text("CREATE TEMP TABLE IF NOT EXISTS lifecycle_test (id INT, val TEXT);")
            )
            await session.execute(
                text("INSERT INTO lifecycle_test (id, val) VALUES (1, 'committed');")
            )
            await session.commit()

        # Step 2: Attempt to insert row B but rollback
        async with session_factory() as session:
            await session.execute(
                text("INSERT INTO lifecycle_test (id, val) VALUES (2, 'aborted');")
            )
            await session.rollback()

        # Step 3: Verify row A persisted and row B was discarded
        async with session_factory() as session:
            res = await session.execute(text("SELECT id, val FROM lifecycle_test ORDER BY id;"))
            rows = res.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 1
            assert rows[0][1] == "committed"
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_transaction_local_tenant_context(
    integration_settings: Settings,
) -> None:
    """Verify that set_tenant_context sets app.current_tenant_id locally and clears on commit."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = uuid.uuid4()

    try:
        # Within transaction: tenant context is visible
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            res = await session.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            assert res.scalar() == str(tenant_id)
            await session.commit()

        # New transaction on new session: tenant context is automatically cleared by PostgreSQL
        async with session_factory() as session:
            res = await session.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            tid = res.scalar()
            assert tid is None or tid == ""
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_tenant_context_does_not_leak_across_pooled_connection_reuse(
    integration_settings: Settings,
) -> None:
    """Verify that pooled connections cannot leak tenant context when reused across sessions."""
    # Force single connection pool with zero overflow to guarantee physical connection reuse
    single_conn_engine = create_async_engine(
        integration_settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=single_conn_engine, class_=AsyncSession, autoflush=False
    )

    tenant_alpha = uuid.uuid4()
    tenant_beta = uuid.uuid4()

    try:
        # Session 1: Tenant Alpha operates and commits
        async with session_factory() as session_1:
            await set_tenant_context(session_1, tenant_alpha)
            res = await session_1.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            assert res.scalar() == str(tenant_alpha)
            await session_1.commit()

        # Session 2: Checks out the EXACT SAME physical connection from pool
        # Context MUST be empty before any tenant context is set
        async with session_factory() as session_2:
            res = await session_2.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            initial_tid = res.scalar()
            assert (
                initial_tid is None or initial_tid == ""
            ), f"Tenant context leaked across pool checkin! Found: {initial_tid}"

            # Tenant Beta operates and rolls back
            await set_tenant_context(session_2, tenant_beta)
            res = await session_2.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            assert res.scalar() == str(tenant_beta)
            await session_2.rollback()

        # Session 3: Reuses physical connection after rollback
        async with session_factory() as session_3:
            res = await session_3.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            final_tid = res.scalar()
            assert (
                final_tid is None or final_tid == ""
            ), f"Tenant context leaked after rollback! Found: {final_tid}"
    finally:
        await single_conn_engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_deliberate_session_level_tenant_context_cannot_leak_across_pool(
    integration_settings: Settings,
) -> None:
    """Deliberately set session-scoped tenant context (is_local=False) and verify it cannot leak across pool checkout."""
    single_conn_engine = create_async_engine(
        integration_settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    register_pool_cleanup_listener(single_conn_engine)
    session_factory = async_sessionmaker(
        bind=single_conn_engine, class_=AsyncSession, autoflush=False
    )

    deliberate_tenant = uuid.uuid4()

    try:
        # Session 1: Deliberately set session-scoped tenant context (is_local=False) and commit
        async with session_factory() as session_1:
            await session_1.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, false);"),
                {"tenant_id": str(deliberate_tenant)},
            )
            res = await session_1.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            assert res.scalar() == str(deliberate_tenant)
            await session_1.commit()

        # Session 1 ends -> connection returned to pool -> checkin listener resets & commits app.current_tenant_id = ''

        # Session 2: Check out the exact same physical connection from pool
        async with session_factory() as session_2:
            res = await session_2.execute(
                text("SELECT current_setting('app.current_tenant_id', true) AS tid;")
            )
            tid = res.scalar()
            assert (
                tid is None or tid == ""
            ), f"Deliberate session-level tenant context leaked across pooled connection reuse! Found: {tid}"
    finally:
        await single_conn_engine.dispose()


@skip_if_no_postgres
def test_alembic_upgrade_head_and_revision_state(
    integration_settings: Settings,
) -> None:
    """Verify that Alembic connects to live PostgreSQL without error swallowing, reporting revision state honestly."""
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", integration_settings.DATABASE_URL)

    # Inspect script directory for available schema migration revisions
    script = ScriptDirectory.from_config(alembic_cfg)
    available_revisions = list(script.walk_revisions())

    # If revisions exist, execute upgrade directly (NO try/except; any failure immediately fails test)
    if available_revisions:
        command.upgrade(alembic_cfg, "head")
        command.heads(alembic_cfg)
        heads = script.get_heads()
        assert len(heads) > 0
    else:
        command.current(alembic_cfg)
        assert len(available_revisions) == 0


class FakeIntegrationRedis:
    """Mock Redis client providing set, get, delete, eval, incr, and expire for integration tests."""

    def __init__(self, initial_data: dict[str, str] | None = None) -> None:
        self.data: dict[str, str] = dict(initial_data or {})

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
        **kwargs: object,
    ) -> bool:
        if nx and key in self.data:
            return False
        self.data[key] = str(value)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if self.data.pop(k, None) is not None:
                count += 1
        return count

    async def incr(self, key: str) -> int:
        val = int(self.data.get(key, "0")) + 1
        self.data[key] = str(val)
        return val

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def eval(self, script: str, numkeys: int, *args: object) -> int:
        return 1


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_concurrent_refresh_token_rotation_serializes_and_detects_reuse(
    integration_settings: Settings,
) -> None:
    """Verify that concurrent refresh token rotations serialize via row lock and detect token reuse."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    user_id = generate_uuid7()
    session_id = generate_uuid7()
    raw_refresh_token = generate_secure_token(32)
    initial_hash = hash_token(raw_refresh_token)

    try:
        async with session_factory() as session:
            user = User(
                id=user_id,
                email=f"concur_refresh_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Concur",
                last_name="Refresh",
                is_active=True,
                token_version=1,
            )
            session.add(user)
            user_session = UserSession(
                id=session_id,
                user_id=user_id,
                refresh_token_hash=initial_hash,
                expires_at=utc_now() + timedelta(days=7),
                token_version=1,
                is_revoked=False,
            )
            session.add(user_session)
            await session.commit()

        fake_redis = FakeIntegrationRedis()

        async def do_refresh() -> dict[str, object]:
            async with session_factory() as sess:
                return await refresh_session_tokens(
                    db=sess,
                    redis=fake_redis,  # type: ignore[arg-type]
                    refresh_token_str=raw_refresh_token,
                    client_ip="127.0.0.1",
                    settings=integration_settings,
                )

        results = await asyncio.gather(do_refresh(), do_refresh(), return_exceptions=True)

        succeeded = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        assert len(succeeded) == 1, f"Expected 1 success, got {len(succeeded)}: {results}"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}: {results}"
        assert isinstance(errors[0], AuthenticationException)
        assert errors[0].code == "TOKEN_REUSE_DETECTED"

        # Verify session is revoked in database due to reuse detection
        async with session_factory() as session:
            stmt = select(UserSession).where(UserSession.id == session_id)
            db_sess = (await session.execute(stmt)).scalar_one()
            assert db_sess.is_revoked is True
            assert db_sess.previous_refresh_token_hash == initial_hash
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_concurrent_backup_code_redemption_serializes(
    integration_settings: Settings,
) -> None:
    """Verify that concurrent backup code redemptions serialize via row lock and prevent double-consumption."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    user_id = generate_uuid7()
    backup_codes = generate_backup_codes(count=10)
    target_code = backup_codes[0]
    hashed_codes = [hash_backup_code(c) for c in backup_codes]

    totp_secret = generate_totp_secret()
    encrypted_secret = encrypt_mfa_secret(totp_secret, integration_settings.MFA_ENCRYPTION_KEY)

    try:
        async with session_factory() as session:
            user = User(
                id=user_id,
                email=f"concur_mfa_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Concur",
                last_name="MFA",
                is_active=True,
                mfa_enabled=True,
                mfa_secret=encrypted_secret,
                mfa_backup_codes=hashed_codes,
                token_version=1,
            )
            session.add(user)
            await session.commit()

        challenge_token_1 = generate_secure_token(32)
        challenge_token_2 = generate_secure_token(32)
        challenge_payload = json.dumps(
            {
                "user_id": str(user_id),
                "organization_slug": None,
                "ip": "127.0.0.1",
                "user_agent": "test-agent",
            }
        )

        fake_redis = FakeIntegrationRedis(
            {
                f"mfa_challenge:{challenge_token_1}": challenge_payload,
                f"mfa_challenge:{challenge_token_2}": challenge_payload,
            }
        )

        async def do_verify(token: str) -> dict[str, object]:
            async with session_factory() as sess:
                return await verify_mfa_challenge(
                    db=sess,
                    redis=fake_redis,  # type: ignore[arg-type]
                    challenge_token=token,
                    code=target_code,
                    settings=integration_settings,
                )

        results = await asyncio.gather(
            do_verify(challenge_token_1),
            do_verify(challenge_token_2),
            return_exceptions=True,
        )

        succeeded = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        assert len(succeeded) == 1, f"Expected exactly 1 redemption, got: {results}"
        assert len(errors) == 1
        assert isinstance(errors[0], AuthenticationException)
        assert errors[0].code == "MFA_INVALID_CODE"

        # Verify backup code list in DB now has 9 codes remaining and target code cannot be verified
        async with session_factory() as session:
            stmt = select(User).where(User.id == user_id)
            db_user = (await session.execute(stmt)).scalar_one()
            assert len(db_user.mfa_backup_codes) == 9
            assert verify_backup_code(target_code, db_user.mfa_backup_codes) == -1
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_cross_tenant_role_assignment_trigger_rejection(
    integration_settings: Settings,
) -> None:
    """Verify that PostgreSQL trigger trg_enforce_membership_role_tenant rejects cross-tenant role assignment."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_a_id = generate_uuid7()
    tenant_b_id = generate_uuid7()
    user_id = generate_uuid7()
    custom_role_b_id = generate_uuid7()

    try:
        async with session_factory() as session:
            # Create Tenant A and Tenant B
            org_a = Organization(
                id=tenant_a_id,
                name="Tenant Alpha",
                slug=f"alpha-{tenant_a_id.hex[:6]}",
                status="active",
            )
            org_b = Organization(
                id=tenant_b_id,
                name="Tenant Beta",
                slug=f"beta-{tenant_b_id.hex[:6]}",
                status="active",
            )
            session.add_all([org_a, org_b])

            # Create User
            user = User(
                id=user_id,
                email=f"user_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Cross",
                last_name="Tenant",
                is_active=True,
            )
            session.add(user)

            # Create Custom Role belonging to Tenant B (is_system = False)
            role_b = Role(
                id=custom_role_b_id,
                name=f"custom_role_{tenant_b_id.hex[:6]}",
                description="Custom role for Tenant B",
                is_system=False,
                tenant_id=tenant_b_id,
            )
            session.add(role_b)
            await session.commit()

        # Attempt to create an organization_membership linking Tenant A with custom_role_b (from Tenant B)
        # The database trigger trg_enforce_membership_role_tenant MUST reject this with check_violation
        with pytest.raises(DBAPIError) as exc_info:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_a_id)
                invalid_membership = OrganizationMembership(
                    id=generate_uuid7(),
                    tenant_id=tenant_a_id,
                    user_id=user_id,
                    role_id=custom_role_b_id,
                    is_active=True,
                )
                session.add(invalid_membership)
                await session.commit()

        error_message = str(exc_info.value)
        assert (
            "Cross-tenant role assignment prohibited" in error_message
            or "check_violation" in error_message.lower()
        )
    finally:
        await engine.dispose()
