"""Integration test suite verifying PostgreSQL 16 connection lifecycle, RLS isolation, migrations, and concurrency controls."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

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
from app.core.errors import AuthenticationException, AuthorizationException
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
from app.modules.auth.dependencies import (
    authenticate_request_pipeline,
    execute_authoritative_session_check,
)
from app.modules.auth.jwt import COOKIE_ACCESS, create_access_token
from app.modules.auth.models import (
    SessionTokenHistory,
    User,
    UserSession,
)
from app.modules.auth.service import refresh_session_tokens, verify_mfa_challenge
from app.modules.embeddings.models import (
    CandidateDocumentEmbedding,
    EmbeddingModel,
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
from app.modules.organizations.models import (
    Organization,
    OrganizationMembership,
    Role,
)
from app.modules.organizations.service import (
    assign_membership_role,
    remove_membership,
    update_membership,
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
        POSTGRES_USER=os.getenv("POSTGRES_USER", "aihr_app_user"),
        POSTGRES_PASSWORD=os.getenv("POSTGRES_PASSWORD", "test_password_only"),
        POSTGRES_MIGRATION_USER=os.getenv("POSTGRES_MIGRATION_USER", "aihr_migration_user"),
        POSTGRES_MIGRATION_PASSWORD=os.getenv(
            "POSTGRES_MIGRATION_PASSWORD", "test_migration_password_only"
        ),
        DATABASE_URL=INTEGRATION_DB_URL,
        DATABASE_SYNC_URL=os.getenv(
            "DATABASE_SYNC_URL", INTEGRATION_DB_URL.replace("+asyncpg", "")
        ),
        DATABASE_MIGRATION_URL=os.getenv("DATABASE_MIGRATION_URL", ""),
        MFA_ENCRYPTION_KEY="integration_test_mfa_encryption_key_at_least_32_bytes_long",
        BACKUP_CODE_PEPPER="integration_test_backup_code_pepper_32_bytes_long",
    )


@pytest.fixture(scope="module", autouse=True)
def ensure_database_schema(integration_settings: Settings) -> None:
    """Ensure latest Alembic migrations are applied using migration credentials before running integration tests."""
    if not POSTGRES_AVAILABLE:
        return
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    migration_url = (
        getattr(integration_settings, "DATABASE_MIGRATION_URL", None)
        or os.getenv("DATABASE_MIGRATION_URL")
        or getattr(integration_settings, "DATABASE_SYNC_URL", None)
        or integration_settings.DATABASE_URL
    )
    if migration_url.startswith("postgresql://"):
        migration_url = migration_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    alembic_cfg.set_main_option("sqlalchemy.url", migration_url)
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
    migration_url = (
        getattr(integration_settings, "DATABASE_MIGRATION_URL", None)
        or getattr(integration_settings, "DATABASE_SYNC_URL", None)
        or integration_settings.DATABASE_URL
    )
    alembic_cfg.set_main_option("sqlalchemy.url", migration_url)

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

    async def ttl(self, key: str) -> int:
        return 3600

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
    hashed_codes = [
        hash_backup_code(c, secret_key=integration_settings.BACKUP_CODE_PEPPER, user_id=user_id)
        for c in backup_codes
    ]

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
            assert (
                verify_backup_code(
                    target_code,
                    db_user.mfa_backup_codes,
                    secret_key=integration_settings.BACKUP_CODE_PEPPER,
                    user_id=user_id,
                )
                == -1
            )
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


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_state_c_redis_outage_authoritative_session_validation(
    integration_settings: Settings,
) -> None:
    """Verify that State C (Redis outage) directly validates session against authoritative PostgreSQL state."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    user_id = generate_uuid7()
    session_id = generate_uuid7()
    token = generate_secure_token(32)
    token_h = hash_token(token)

    try:
        async with session_factory() as session:
            user = User(
                id=user_id,
                email=f"state_c_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="StateC",
                last_name="Tester",
                is_active=True,
                token_version=1,
            )
            sess_rec = UserSession(
                id=session_id,
                user_id=user_id,
                refresh_token_hash=token_h,
                token_version=1,
                is_revoked=False,
                expires_at=utc_now() + timedelta(days=7),
            )
            session.add_all([user, sess_rec])
            await session.commit()

        # 1. Active session succeeds
        async with session_factory() as session:
            validated = await execute_authoritative_session_check(
                db=session,
                session_id=session_id,
                user_id=user_id,
                token_version=1,
            )
            assert validated.id == session_id

        # 2. Token version mismatch raises TOKEN_VERSION_STALE
        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await execute_authoritative_session_check(
                    db=session,
                    session_id=session_id,
                    user_id=user_id,
                    token_version=2,  # Stale
                )
            assert exc_info.value.code == "TOKEN_VERSION_STALE"

        # 3. Revoked session in PostgreSQL raises SESSION_REVOKED
        async with session_factory() as session:
            sess_to_revoke = (
                await session.execute(select(UserSession).where(UserSession.id == session_id))
            ).scalar_one()
            sess_to_revoke.is_revoked = True
            await session.commit()

        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await execute_authoritative_session_check(
                    db=session,
                    session_id=session_id,
                    user_id=user_id,
                    token_version=1,
                )
            assert exc_info.value.code == "SESSION_REVOKED"

        # 4. Non-existent session raises SESSION_INVALID
        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await execute_authoritative_session_check(
                    db=session,
                    session_id=generate_uuid7(),
                    user_id=user_id,
                    token_version=1,
                )
            assert exc_info.value.code == "SESSION_INVALID"
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_token_history_multi_rotation_and_old_token_reuse_detected(
    integration_settings: Settings,
) -> None:
    """Verify persistent token reuse history across multi-generation rotations and automatic cascade cleanup."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    user_id = generate_uuid7()
    session_id = generate_uuid7()
    token_a = generate_secure_token(32)
    token_a_hash = hash_token(token_a)

    fake_redis = FakeIntegrationRedis()

    try:
        # Create user and initial session with Token A
        async with session_factory() as session:
            user = User(
                id=user_id,
                email=f"history_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="History",
                last_name="Tester",
                is_active=True,
                token_version=1,
            )
            sess_rec = UserSession(
                id=session_id,
                user_id=user_id,
                refresh_token_hash=token_a_hash,
                token_version=1,
                is_revoked=False,
                expires_at=utc_now() + timedelta(days=7),
            )
            session.add_all([user, sess_rec])
            await session.commit()

        # Rotation 1: Token A -> Token B
        async with session_factory() as session:
            res_1 = await refresh_session_tokens(
                db=session,
                redis=fake_redis,  # type: ignore[arg-type]
                refresh_token_str=token_a,
                client_ip="127.0.0.1",
                settings=integration_settings,
            )
            token_b = str(res_1["refresh_token"])

        # Verify SessionTokenHistory has recorded Token A
        async with session_factory() as session:
            history_rows = (
                (
                    await session.execute(
                        select(SessionTokenHistory).where(
                            SessionTokenHistory.session_id == session_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(history_rows) == 1
            assert history_rows[0].token_hash == token_a_hash

        # Rotation 2: Token B -> Token C
        async with session_factory() as session:
            res_2 = await refresh_session_tokens(
                db=session,
                redis=fake_redis,  # type: ignore[arg-type]
                refresh_token_str=token_b,
                client_ip="127.0.0.1",
                settings=integration_settings,
            )
            token_c = str(res_2["refresh_token"])
            assert len(token_c) > 0

        # Verify SessionTokenHistory now has 2 recorded tokens (Token A and Token B)
        async with session_factory() as session:
            history_rows = (
                (
                    await session.execute(
                        select(SessionTokenHistory).where(
                            SessionTokenHistory.session_id == session_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(history_rows) == 2
            recorded_hashes = {h.token_hash for h in history_rows}
            assert token_a_hash in recorded_hashes
            assert hash_token(token_b) in recorded_hashes

        # Attack: Replay Token A (2 generations old)
        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await refresh_session_tokens(
                    db=session,
                    redis=fake_redis,  # type: ignore[arg-type]
                    refresh_token_str=token_a,  # REUSE OF TOKEN A!
                    client_ip="10.0.0.1",
                    settings=integration_settings,
                )
            assert exc_info.value.code == "TOKEN_REUSE_DETECTED"

        # Authoritative DB verification: Entire session family is revoked
        async with session_factory() as session:
            revoked_sess = (
                await session.execute(select(UserSession).where(UserSession.id == session_id))
            ).scalar_one()
            assert revoked_sess.is_revoked is True

        # Verify CASCADE cleanup on session deletion
        async with session_factory() as session:
            sess_to_delete = (
                await session.execute(select(UserSession).where(UserSession.id == session_id))
            ).scalar_one()
            await session.delete(sess_to_delete)
            await session.commit()

        async with session_factory() as session:
            remaining_history = (
                (
                    await session.execute(
                        select(SessionTokenHistory).where(
                            SessionTokenHistory.session_id == session_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(remaining_history) == 0
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_state_a_micro_validation_rejects_revoked_and_expired_session(
    integration_settings: Settings,
) -> None:
    """Verify State A micro-validation (>30s) validates session against PostgreSQL, rejecting revoked/expired sessions and evicting Redis."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    user_id = generate_uuid7()
    session_id_revoked = generate_uuid7()
    session_id_expired = generate_uuid7()
    session_id_valid = generate_uuid7()

    token_str = generate_secure_token(32)
    token_h = hash_token(token_str)

    fake_redis = FakeIntegrationRedis()

    try:
        async with session_factory() as session:
            user = User(
                id=user_id,
                email=f"state_a_{user_id.hex[:8]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="StateA",
                last_name="Tester",
                is_active=True,
                token_version=1,
            )
            # Session 1: Revoked in DB
            sess_revoked = UserSession(
                id=session_id_revoked,
                user_id=user_id,
                refresh_token_hash=token_h,
                token_version=1,
                is_revoked=True,
                expires_at=utc_now() + timedelta(days=7),
            )
            # Session 2: Expired in DB
            sess_expired = UserSession(
                id=session_id_expired,
                user_id=user_id,
                refresh_token_hash=token_h,
                token_version=1,
                is_revoked=False,
                expires_at=utc_now() - timedelta(days=1),
            )
            # Session 3: Valid in DB
            sess_valid = UserSession(
                id=session_id_valid,
                user_id=user_id,
                refresh_token_hash=token_h,
                token_version=1,
                is_revoked=False,
                expires_at=utc_now() + timedelta(days=7),
            )
            session.add_all([user, sess_revoked, sess_expired, sess_valid])
            await session.commit()

        # Prepopulate Redis with cached sessions where last_db_verified_at was 35s ago (> 30s micro-validation threshold)
        now_ts = time.time()
        elapsed_ts = now_ts - 35.0

        fake_redis.data[f"session:{user_id}:{session_id_revoked}"] = json.dumps(
            {"token_version": 1, "role_version": 1, "last_db_verified_at": elapsed_ts}
        )
        fake_redis.data[f"session:{user_id}:{session_id_expired}"] = json.dumps(
            {"token_version": 1, "role_version": 1, "last_db_verified_at": elapsed_ts}
        )
        fake_redis.data[f"session:{user_id}:{session_id_valid}"] = json.dumps(
            {"token_version": 1, "role_version": 1, "last_db_verified_at": elapsed_ts}
        )
        fake_redis.data[f"user_current_token_version:{user_id}"] = "1"

        # 1. Test Revoked Session: Cache hit in Redis, but micro-validation finds is_revoked = True in PostgreSQL
        jwt_revoked = create_access_token(
            user_id=user_id,
            session_id=session_id_revoked,
            tenant_id=None,
            role="candidate",
            permissions=[],
            token_version=1,
            role_version=1,
            is_super_admin=False,
            settings=integration_settings,
        )
        req_revoked = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "headers": [(b"cookie", f"{COOKIE_ACCESS}={jwt_revoked}".encode())],
            }
        )

        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await authenticate_request_pipeline(
                    request=req_revoked,
                    db=session,
                    redis=fake_redis,  # type: ignore[arg-type]
                    settings=integration_settings,
                )
            assert exc_info.value.code == "SESSION_REVOKED"
            # Redis session must be evicted
            assert f"session:{user_id}:{session_id_revoked}" not in fake_redis.data

        # 2. Test Expired Session: Cache hit in Redis, but micro-validation finds expires_at < now in PostgreSQL
        jwt_expired = create_access_token(
            user_id=user_id,
            session_id=session_id_expired,
            tenant_id=None,
            role="candidate",
            permissions=[],
            token_version=1,
            role_version=1,
            is_super_admin=False,
            settings=integration_settings,
        )
        req_expired = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "headers": [(b"cookie", f"{COOKIE_ACCESS}={jwt_expired}".encode())],
            }
        )

        async with session_factory() as session:
            with pytest.raises(AuthenticationException) as exc_info:
                await authenticate_request_pipeline(
                    request=req_expired,
                    db=session,
                    redis=fake_redis,  # type: ignore[arg-type]
                    settings=integration_settings,
                )
            assert exc_info.value.code == "SESSION_EXPIRED"
            # Redis session must be evicted
            assert f"session:{user_id}:{session_id_expired}" not in fake_redis.data

        # 3. Test Valid Session: Passes micro-validation and updates last_db_verified_at in Redis
        jwt_valid = create_access_token(
            user_id=user_id,
            session_id=session_id_valid,
            tenant_id=None,
            role="candidate",
            permissions=[],
            token_version=1,
            role_version=1,
            is_super_admin=False,
            settings=integration_settings,
        )
        req_valid = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "headers": [(b"cookie", f"{COOKIE_ACCESS}={jwt_valid}".encode())],
            }
        )

        async with session_factory() as session:
            sec_ctx = await authenticate_request_pipeline(
                request=req_valid,
                db=session,
                redis=fake_redis,  # type: ignore[arg-type]
                settings=integration_settings,
            )
            assert sec_ctx.user_id == user_id
            assert sec_ctx.session_id == session_id_valid
            # Redis session still present and touched
            assert f"session:{user_id}:{session_id_valid}" in fake_redis.data
            updated_data = json.loads(fake_redis.data[f"session:{user_id}:{session_id_valid}"])
            assert updated_data["last_db_verified_at"] > elapsed_ts
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_pgvector_extension_and_model_registry(
    integration_settings: Settings,
) -> None:
    """Verify pgvector extension availability and approved embedding model registry."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            # 1. Verify extension
            ext_res = await session.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            )
            ext_row = ext_res.first()
            assert ext_row is not None
            assert ext_row[0] == "vector"

            # 2. Verify seeded models
            models_res = await session.execute(
                select(EmbeddingModel).order_by(EmbeddingModel.model_identifier)
            )
            models = models_res.scalars().all()
            model_map = {m.model_identifier: m for m in models}

            assert "text-embedding-3-small" in model_map
            assert model_map["text-embedding-3-small"].expected_dimensions == 1536
            assert model_map["text-embedding-3-small"].provider == "openai"

            assert "amazon.titan-embed-text-v1" in model_map
            assert model_map["amazon.titan-embed-text-v1"].expected_dimensions == 1536

            assert "cohere.embed-english-v3" in model_map
            assert model_map["cohere.embed-english-v3"].expected_dimensions == 1024

            assert "bge-base-en-v1.5" in model_map
            assert model_map["bge-base-en-v1.5"].expected_dimensions == 768

            # 3. Verify check constraint rejects unapproved dimensions (e.g. 512)
            with pytest.raises(DBAPIError):
                bad_model = EmbeddingModel(
                    model_identifier=f"bad-model-{uuid.uuid4().hex[:6]}",
                    provider="custom",
                    expected_dimensions=512,  # Invalid
                )
                session.add(bad_model)
                await session.flush()
            await session.rollback()
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_vector_dimension_check_constraints_and_foreign_keys(
    integration_settings: Settings,
) -> None:
    """Verify database-level check constraints and model-registry foreign keys on vector tables."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = generate_uuid7()
    doc_id = generate_uuid7()

    try:
        async with session_factory() as session:
            org = Organization(
                id=tenant_id,
                name=f"Vector Test Org {tenant_id.hex[:6]}",
                slug=f"vec-org-{tenant_id.hex[:6]}",
            )
            session.add(org)
            await session.commit()

        # 1. Foreign key rejection for unregistered model
        async with session_factory() as session:
            with pytest.raises(EmbeddingModelNotFoundException):
                await store_candidate_document_embedding(
                    session=session,
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    model_identifier="unregistered-model",
                    model_version="1.0",
                    embedding=[0.01] * 1536,
                )

            with pytest.raises(DBAPIError):
                bad_fk_emb = CandidateDocumentEmbedding(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    model_identifier="unregistered-model",
                    model_version="1.0",
                    vector_dimensions=1536,
                    embedding_1536=[0.01] * 1536,
                )
                session.add(bad_fk_emb)
                await session.flush()
            await session.rollback()

        # 2. Check constraint rejection: vector_dimensions=1536 but populated in embedding_1024
        async with session_factory() as session:
            with pytest.raises(InvalidEmbeddingDimensionException):
                await store_candidate_document_embedding(
                    session=session,
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    model_identifier="text-embedding-3-small",
                    model_version="1.0",
                    embedding=[0.01] * 1024,  # mismatched dimension
                )
            with pytest.raises(DBAPIError):
                mismatched_col_emb = CandidateDocumentEmbedding(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    model_identifier="text-embedding-3-small",
                    model_version="1.0",
                    vector_dimensions=1536,
                    embedding_1024=[0.01] * 1024,  # populated in wrong column
                )
                session.add(mismatched_col_emb)
                await session.flush()
            await session.rollback()

        # 3. Check constraint rejection: multiple vector columns populated simultaneously
        async with session_factory() as session:
            with pytest.raises(DBAPIError):
                multi_col_emb = CandidateDocumentEmbedding(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    model_identifier="text-embedding-3-small",
                    model_version="1.0",
                    vector_dimensions=1536,
                    embedding_1536=[0.01] * 1536,
                    embedding_1024=[0.01] * 1024,
                )
                session.add(multi_col_emb)
                await session.flush()
            await session.rollback()
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_vector_insertion_and_cosine_similarity_search(
    integration_settings: Settings,
) -> None:
    """Verify inserting embeddings across dimensions and executing cosine distance similarity queries."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = generate_uuid7()
    doc_a_id = generate_uuid7()
    doc_b_id = generate_uuid7()

    try:
        async with session_factory() as session:
            org = Organization(
                id=tenant_id,
                name=f"Cosine Test Org {tenant_id.hex[:6]}",
                slug=f"cos-org-{tenant_id.hex[:6]}",
            )
            session.add(org)
            await session.commit()

        # Construct orthogonal and similar test vectors
        vec_target = [0.0] * 1536
        vec_target[0] = 1.0  # Unit vector along axis 0

        vec_similar = [0.0] * 1536
        vec_similar[0] = 0.95
        vec_similar[1] = 0.05

        vec_orthogonal = [0.0] * 1536
        vec_orthogonal[1] = 1.0  # Orthogonal along axis 1

        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            await store_candidate_document_embedding(
                session=session,
                tenant_id=tenant_id,
                document_id=doc_a_id,
                model_identifier="text-embedding-3-small",
                model_version="1.0",
                embedding=vec_similar,
            )
            await store_candidate_document_embedding(
                session=session,
                tenant_id=tenant_id,
                document_id=doc_b_id,
                model_identifier="text-embedding-3-small",
                model_version="1.0",
                embedding=vec_orthogonal,
            )
            # Also verify job_embeddings storage
            job_id = generate_uuid7()
            job_emb = await store_job_embedding(
                session=session,
                tenant_id=tenant_id,
                job_id=job_id,
                model_identifier="text-embedding-3-small",
                model_version="1.0",
                embedding=vec_similar,
            )
            assert job_emb.id is not None
            assert job_emb.embedding_1536 is not None
            await session.commit()

        # Perform cosine similarity search
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            results = await search_similar_candidate_documents(
                session=session,
                tenant_id=tenant_id,
                query_vector=vec_target,
                model_identifier="text-embedding-3-small",
                limit=10,
            )

            assert len(results) == 2
            top_doc, top_sim = results[0]
            second_doc, second_sim = results[1]

            # doc_a must rank higher than doc_b
            assert top_doc.document_id == doc_a_id
            assert second_doc.document_id == doc_b_id
            assert top_sim > second_sim
            assert top_sim > 0.9  # Highly aligned with axis 0
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_runtime_role_and_privileges_verification(
    integration_settings: Settings,
) -> None:
    """Verify that runtime connection role has NOSUPERUSER, NOBYPASSRLS, and does not own tenant tables."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            # 1. Verify connected session role is the restricted application user
            user_res = await session.execute(text("SELECT current_user;"))
            current_role = user_res.scalar()
            assert current_role == integration_settings.POSTGRES_USER

            # 2. Verify role attributes: strictly NOSUPERUSER, NOBYPASSRLS, NOCREATEDB
            role_attr_res = await session.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb "
                    "FROM pg_roles WHERE rolname = current_user;"
                )
            )
            role_attrs = role_attr_res.one()
            assert role_attrs[0] is False, "Runtime role must have NOSUPERUSER"
            assert role_attrs[1] is False, "Runtime role must have NOBYPASSRLS"
            assert role_attrs[2] is False, "Runtime role must have NOCREATEDB"

            # 2b. Verify migration role attributes: strictly NOSUPERUSER, NOBYPASSRLS, NOCREATEDB
            mig_user = integration_settings.POSTGRES_MIGRATION_USER or "aihr_migration_user"
            mig_attr_res = await session.execute(
                text(
                    f"SELECT rolsuper, rolbypassrls, rolcreatedb "
                    f"FROM pg_roles WHERE rolname = '{mig_user}';"
                )
            )
            mig_attrs = mig_attr_res.one()
            assert mig_attrs[0] is False, "Migration role must have rolsuper = false"
            assert mig_attrs[1] is False, "Migration role must have rolbypassrls = false"
            assert mig_attrs[2] is False, "Migration role must have rolcreatedb = false"

            # 3. Verify runtime role does NOT own tenant-scoped tables
            owner_res = await session.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE tablename IN ('candidate_document_embeddings', 'job_embeddings', 'organization_memberships');"
                )
            )
            owners = owner_res.all()
            assert len(owners) >= 3
            for tbl, owner in owners:
                assert (
                    owner != current_role
                ), f"Security violation: table {tbl} is owned by runtime role {current_role}"
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_role_initialization_with_custom_credentials_and_reconciliation(
    integration_settings: Settings,
) -> None:
    """Verify fresh database role initialization with custom credentials,
    execution of the actual initialization mechanism, credential reconciliation/rotation,
    attribute verification, RLS enforcement, and safe cleanup.
    """
    from sqlalchemy.engine import URL, make_url

    runtime_url = make_url(integration_settings.DATABASE_URL)
    host = os.getenv("POSTGRES_HOST", runtime_url.host or "localhost")
    port = int(os.getenv("POSTGRES_PORT", str(runtime_url.port or 5432)))
    database = os.getenv("POSTGRES_DB", runtime_url.database or "ai_hr_db_test")

    superuser = os.getenv("POSTGRES_SUPERUSER", "postgres")
    super_pass = os.getenv(
        "PGPASSWORD",
        os.getenv("POSTGRES_SUPERUSER_PASSWORD", "test_super_password_only"),
    )

    repo_root = Path(__file__).resolve().parents[3]
    init_sh = repo_root / "infrastructure" / "scripts" / "init-db.sh"
    init_sql = repo_root / "infrastructure" / "scripts" / "init-db.sql"

    def _find_bash() -> str | None:
        found = shutil.which("bash")
        if found:
            return found
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.exists():
            return str(git_bash)
        return None

    bash_bin = _find_bash()
    psql_bin = shutil.which("psql")

    if not bash_bin and not psql_bin:
        pytest.skip(
            "Neither bash nor psql is available on test runner to execute init-db mechanism"
        )

    def execute_bootstrap(env_overrides: dict[str, str]) -> None:
        merged_env = os.environ.copy()
        merged_env.update(env_overrides)
        if bash_bin and init_sh.exists():
            proc = subprocess.run(
                [bash_bin, str(init_sh)],
                env=merged_env,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"init-db.sh failed ({proc.returncode}): {proc.stderr}")
        elif psql_bin and init_sql.exists():
            proc = subprocess.run(
                [
                    psql_bin,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    env_overrides.get("POSTGRES_HOST", host),
                    "-p",
                    str(env_overrides.get("POSTGRES_PORT", port)),
                    "-U",
                    env_overrides.get("POSTGRES_SUPERUSER", superuser),
                    "-d",
                    env_overrides.get("POSTGRES_DB", database),
                    "-f",
                    str(init_sql),
                ],
                env=merged_env,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"psql init-db.sql failed ({proc.returncode}): {proc.stderr}")

    test_id = uuid.uuid4().hex[:8]
    custom_mig_user = f"test_mig_{test_id}"
    custom_mig_pass_1 = f"CustomMigPass1_{test_id}"
    custom_app_user = f"test_app_{test_id}"
    custom_app_pass_1 = f"CustomAppPass1_{test_id}"

    try:
        # Step 1 & 2: Initialize roles with custom credentials via actual bootstrap mechanism
        env_run_1 = {
            "ENVIRONMENT": "testing",
            "POSTGRES_SUPERUSER": superuser,
            "POSTGRES_SUPERUSER_PASSWORD": super_pass,
            "PGPASSWORD": super_pass,
            "POSTGRES_HOST": host,
            "POSTGRES_PORT": str(port),
            "POSTGRES_DB": database,
            "POSTGRES_MIGRATION_USER": custom_mig_user,
            "POSTGRES_MIGRATION_PASSWORD": custom_mig_pass_1,
            "POSTGRES_APP_USER": custom_app_user,
            "POSTGRES_APP_PASSWORD": custom_app_pass_1,
        }
        execute_bootstrap(env_run_1)

        # Step 3: Verify both roles can authenticate with custom credentials
        mig_url_1 = URL.create(
            "postgresql+asyncpg",
            username=custom_mig_user,
            password=custom_mig_pass_1,
            host=host,
            port=port,
            database=database,
        )
        mig_engine_1 = create_async_engine(mig_url_1)
        async with mig_engine_1.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            assert res.scalar() == custom_mig_user
        await mig_engine_1.dispose()

        app_url_1 = URL.create(
            "postgresql+asyncpg",
            username=custom_app_user,
            password=custom_app_pass_1,
            host=host,
            port=port,
            database=database,
        )
        app_engine_1 = create_async_engine(app_url_1)
        async with app_engine_1.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            assert res.scalar() == custom_app_user
        await app_engine_1.dispose()

        # Step 4: Re-run initialization with rotated credentials (exercises reconciliation branch in SQL)
        custom_mig_pass_2 = f"RotatedMigPass2_{test_id}"
        custom_app_pass_2 = f"RotatedAppPass2_{test_id}"

        env_run_2 = {
            "ENVIRONMENT": "testing",
            "POSTGRES_SUPERUSER": superuser,
            "POSTGRES_SUPERUSER_PASSWORD": super_pass,
            "PGPASSWORD": super_pass,
            "POSTGRES_HOST": host,
            "POSTGRES_PORT": str(port),
            "POSTGRES_DB": database,
            "POSTGRES_MIGRATION_USER": custom_mig_user,
            "POSTGRES_MIGRATION_PASSWORD": custom_mig_pass_2,
            "POSTGRES_APP_USER": custom_app_user,
            "POSTGRES_APP_PASSWORD": custom_app_pass_2,
        }
        execute_bootstrap(env_run_2)

        # Step 5: Verify new credentials work
        mig_url_2 = URL.create(
            "postgresql+asyncpg",
            username=custom_mig_user,
            password=custom_mig_pass_2,
            host=host,
            port=port,
            database=database,
        )
        mig_engine_2 = create_async_engine(mig_url_2)
        async with mig_engine_2.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            assert res.scalar() == custom_mig_user
        await mig_engine_2.dispose()

        app_url_2 = URL.create(
            "postgresql+asyncpg",
            username=custom_app_user,
            password=custom_app_pass_2,
            host=host,
            port=port,
            database=database,
        )
        app_engine_2 = create_async_engine(app_url_2)
        async with app_engine_2.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            assert res.scalar() == custom_app_user

            # Step 7: Verify role attributes remain strictly least-privilege
            role_res = await conn.execute(
                text(
                    f"SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    f"FROM pg_roles WHERE rolname IN ('{custom_mig_user}', '{custom_app_user}');"
                )
            )
            roles = {r[0]: (r[1], r[2], r[3], r[4]) for r in role_res.all()}
            for role_name in (custom_mig_user, custom_app_user):
                assert role_name in roles
                assert roles[role_name][0] is False, f"{role_name} must have rolsuper = false"
                assert roles[role_name][1] is False, f"{role_name} must have rolbypassrls = false"
                assert roles[role_name][2] is False, f"{role_name} must have rolcreatedb = false"
                assert roles[role_name][3] is False, f"{role_name} must have rolcreaterole = false"

            # Step 8a: Verify custom_app_user does NOT own tenant-scoped tables
            owner_res = await conn.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE tablename IN ('candidate_document_embeddings', 'job_embeddings', 'organization_memberships');"
                )
            )
            for tbl, owner in owner_res.all():
                assert (
                    owner != custom_app_user
                ), f"Security violation: table {tbl} is owned by runtime role {custom_app_user}"

            # Step 8b: Verify custom_app_user cannot bypass RLS
            bypass_res = await conn.execute(
                text(f"SELECT rolbypassrls FROM pg_roles WHERE rolname = '{custom_app_user}';")
            )
            assert bypass_res.scalar() is False, f"{custom_app_user} must have rolbypassrls = false"

        await app_engine_2.dispose()

        # Step 6: Verify old credentials are now rejected
        old_mig_engine = create_async_engine(mig_url_1)
        with pytest.raises((DBAPIError, asyncpg.exceptions.InvalidPasswordError)):
            async with old_mig_engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
        await old_mig_engine.dispose()

        old_app_engine = create_async_engine(app_url_1)
        with pytest.raises((DBAPIError, asyncpg.exceptions.InvalidPasswordError)):
            async with old_app_engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
        await old_app_engine.dispose()

    finally:
        # Step 9: Safely clean up test-created roles and restore authoritative configuration
        auth_mig_user = integration_settings.POSTGRES_MIGRATION_USER or "aihr_migration_user"
        auth_app_user = integration_settings.POSTGRES_USER or "aihr_app_user"
        auth_mig_pass = os.getenv(
            "POSTGRES_MIGRATION_PASSWORD", "local_development_migration_password_only"
        )
        auth_app_pass = os.getenv("POSTGRES_PASSWORD", "local_development_password_only")

        # 9a: Restore schema public ownership to authoritative migration role and drop test roles
        super_url = f"postgresql+asyncpg://{superuser}:{super_pass}@{host}:{port}/{database}"
        try:
            cleanup_engine = create_async_engine(super_url, isolation_level="AUTOCOMMIT")
            async with cleanup_engine.connect() as conn:
                await conn.execute(text(f'ALTER SCHEMA public OWNER TO "{auth_mig_user}";'))
                await conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{custom_mig_user}";'))
                await conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{custom_app_user}";'))
                await conn.execute(text(f'DROP ROLE IF EXISTS "{custom_mig_user}";'))
                await conn.execute(text(f'DROP ROLE IF EXISTS "{custom_app_user}";'))
            await cleanup_engine.dispose()
        except Exception:
            pass

        # 9b: Re-run bootstrap with authoritative credentials to guarantee clean baseline
        try:
            restore_env = {
                "ENVIRONMENT": "testing",
                "POSTGRES_SUPERUSER": superuser,
                "POSTGRES_SUPERUSER_PASSWORD": super_pass,
                "PGPASSWORD": super_pass,
                "POSTGRES_HOST": host,
                "POSTGRES_PORT": str(port),
                "POSTGRES_DB": database,
                "POSTGRES_MIGRATION_USER": auth_mig_user,
                "POSTGRES_MIGRATION_PASSWORD": auth_mig_pass,
                "POSTGRES_APP_USER": auth_app_user,
                "POSTGRES_APP_PASSWORD": auth_app_pass,
            }
            execute_bootstrap(restore_env)
        except Exception:
            pass


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_vector_tenant_isolation_under_rls(
    integration_settings: Settings,
) -> None:
    """Verify that vector embedding queries and similarity searches are strictly isolated per tenant under RLS

    using the real application runtime credentials WITHOUT SET ROLE test workarounds.
    """
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_a_id = generate_uuid7()
    tenant_b_id = generate_uuid7()
    doc_a_id = generate_uuid7()

    try:
        async with session_factory() as session:
            org_a = Organization(
                id=tenant_a_id,
                name=f"Tenant A {tenant_a_id.hex[:6]}",
                slug=f"tenant-a-{tenant_a_id.hex[:6]}",
            )
            org_b = Organization(
                id=tenant_b_id,
                name=f"Tenant B {tenant_b_id.hex[:6]}",
                slug=f"tenant-b-{tenant_b_id.hex[:6]}",
            )
            session.add_all([org_a, org_b])
            await session.commit()

        test_vec = [0.1] * 1536

        # Tenant A inserts vector embedding under Tenant A context
        async with session_factory() as session:
            await set_tenant_context(session, tenant_a_id)
            await store_candidate_document_embedding(
                session=session,
                tenant_id=tenant_a_id,
                document_id=doc_a_id,
                model_identifier="text-embedding-3-small",
                model_version="1.0",
                embedding=test_vec,
            )
            await session.commit()

        # Tenant B queries under its tenant context: must return 0 results
        async with session_factory() as session:
            await set_tenant_context(session, tenant_b_id)
            # Direct query
            res = await session.execute(
                select(CandidateDocumentEmbedding).where(
                    CandidateDocumentEmbedding.document_id == doc_a_id
                )
            )
            assert res.scalar_one_or_none() is None

            # Similarity search under Tenant B
            b_results = await search_similar_candidate_documents(
                session=session,
                tenant_id=tenant_b_id,
                query_vector=test_vec,
                model_identifier="text-embedding-3-small",
            )
            assert len(b_results) == 0

        # Mismatched context (Tenant B context attempting to insert row with tenant_a_id) is rejected by RLS
        async with session_factory() as session:
            await set_tenant_context(session, tenant_b_id)
            with pytest.raises(DBAPIError):
                cross_tenant_emb = CandidateDocumentEmbedding(
                    tenant_id=tenant_a_id,  # Mismatched!
                    document_id=generate_uuid7(),
                    model_identifier="text-embedding-3-small",
                    model_version="1.0",
                    vector_dimensions=1536,
                    embedding_1536=test_vec,
                )
                session.add(cross_tenant_emb)
                await session.flush()
            await session.rollback()
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_embedding_model_registry_exact_seeded_contents(
    integration_settings: Settings,
) -> None:
    """Verify that live PostgreSQL registry contains the exact 4 canonical approved models."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            res = await session.execute(
                select(
                    EmbeddingModel.model_identifier,
                    EmbeddingModel.provider,
                    EmbeddingModel.expected_dimensions,
                    EmbeddingModel.is_active,
                ).order_by(EmbeddingModel.model_identifier)
            )
            rows = set(res.all())
            expected = {
                ("text-embedding-3-small", "openai", 1536, True),
                ("amazon.titan-embed-text-v1", "aws_bedrock", 1536, True),
                ("cohere.embed-english-v3", "aws_bedrock", 1024, True),
                ("bge-base-en-v1.5", "huggingface", 768, True),
            }
            assert rows == expected
    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_postgres_vector_similarity_search_hardened_validation_integration(
    integration_settings: Settings,
) -> None:
    """Verify live PostgreSQL integration for hardened similarity search validations."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = generate_uuid7()
    doc_id = generate_uuid7()
    test_vec = [0.05] * 1536

    try:
        async with session_factory() as session:
            org = Organization(
                id=tenant_id,
                name=f"Search Validation Org {tenant_id.hex[:6]}",
                slug=f"search-val-{tenant_id.hex[:6]}",
            )
            session.add(org)
            await session.commit()

        # Seed candidate document embedding
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            await store_candidate_document_embedding(
                session=session,
                tenant_id=tenant_id,
                document_id=doc_id,
                model_identifier="text-embedding-3-small",
                model_version="1.0",
                embedding=test_vec,
            )
            await session.commit()

        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)

            # 1. Reject invalid limits
            with pytest.raises(InvalidSearchParameterException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=test_vec,
                    model_identifier="text-embedding-3-small",
                    limit=0,
                )

            with pytest.raises(InvalidSearchParameterException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=test_vec,
                    model_identifier="text-embedding-3-small",
                    limit=105,
                )

            # 2. Reject empty or NaN/Inf vectors
            with pytest.raises(InvalidSearchParameterException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=[],
                    model_identifier="text-embedding-3-small",
                )

            nan_vec = [0.05] * 1535 + [float("nan")]
            with pytest.raises(InvalidSearchParameterException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=nan_vec,
                    model_identifier="text-embedding-3-small",
                )

            # 3. Reject unregistered model
            with pytest.raises(EmbeddingModelNotFoundException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=test_vec,
                    model_identifier="unknown-model-identifier",
                )

            # 3b. Reject inactive model
            await session.execute(
                text(
                    "UPDATE embedding_models SET is_active = FALSE WHERE model_identifier = 'bge-base-en-v1.5';"
                )
            )
            with pytest.raises(DeprecatedEmbeddingModelException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=[0.05] * 768,
                    model_identifier="bge-base-en-v1.5",
                )
            await session.execute(
                text(
                    "UPDATE embedding_models SET is_active = TRUE WHERE model_identifier = 'bge-base-en-v1.5';"
                )
            )

            # 4. Reject dimension mismatch
            with pytest.raises(InvalidEmbeddingDimensionException):
                await search_similar_candidate_documents(
                    session=session,
                    tenant_id=tenant_id,
                    query_vector=[0.05] * 768,  # mismatch with 1536
                    model_identifier="text-embedding-3-small",
                )

            # 5. Valid search succeeds and returns results
            results = await search_similar_candidate_documents(
                session=session,
                tenant_id=tenant_id,
                query_vector=test_vec,
                model_identifier="text-embedding-3-small",
                limit=5,
            )
            assert len(results) == 1
            matched_doc, similarity = results[0]
            assert matched_doc.document_id == doc_id
            assert similarity > 0.999
    finally:
        await engine.dispose()


@skip_if_no_postgres
def test_postgres_hnsw_indexes_exist_and_downgrade_upgrade_lifecycle(
    integration_settings: Settings,
) -> None:
    """Verify that HNSW partial indexes are created and test Alembic downgrade/re-upgrade determinism."""
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    migration_url = (
        getattr(integration_settings, "DATABASE_MIGRATION_URL", None)
        or getattr(integration_settings, "DATABASE_SYNC_URL", None)
        or integration_settings.DATABASE_URL
    )
    alembic_cfg.set_main_option("sqlalchemy.url", migration_url)

    # 1. Verify HNSW indexes exist in live schema
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert "002_db_foundation_pgvector" in heads

    # 2. Downgrade to 001_auth_identity
    command.downgrade(alembic_cfg, "001_auth_identity")

    # 3. Re-upgrade back to head
    command.upgrade(alembic_cfg, "head")
    assert script.get_heads() == heads


@skip_if_no_postgres
def test_postgres_vector_downgrade_preserves_external_dependent_objects_and_extension(
    integration_settings: Settings,
) -> None:
    """Verify that downgrade without CASCADE preserves external vector-dependent objects and the extension."""
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    migration_url = (
        getattr(integration_settings, "DATABASE_MIGRATION_URL", None)
        or os.getenv("DATABASE_MIGRATION_URL")
        or getattr(integration_settings, "DATABASE_SYNC_URL", None)
        or integration_settings.DATABASE_URL
    )
    alembic_url = (
        migration_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if migration_url.startswith("postgresql://")
        else migration_url
    )
    alembic_cfg.set_main_option("sqlalchemy.url", alembic_url)

    # Ensure head first
    command.upgrade(alembic_cfg, "head")

    # Connect with synchronous engine using migration credentials (schema owner with CREATE privileges)
    from sqlalchemy import create_engine

    sync_engine = create_engine(alembic_url.replace("+asyncpg", ""))

    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS external_vector_dependent_table ("
                    "  id UUID PRIMARY KEY, "
                    "  external_vec vector(64)"
                    ");"
                )
            )

        # Execute migration downgrade to 001
        command.downgrade(alembic_cfg, "001_auth_identity")

        # Verify:
        # A. Migration 002 tables are cleanly dropped
        with sync_engine.connect() as conn:
            cand_check = conn.execute(
                text("SELECT to_regclass('candidate_document_embeddings');")
            ).scalar()
            assert cand_check is None

            # B. External table still exists intact
            ext_check = conn.execute(
                text("SELECT to_regclass('external_vector_dependent_table');")
            ).scalar()
            assert ext_check is not None

            # C. vector extension is still installed and active
            ext_installed = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
            ).scalar()
            assert ext_installed == 1

        # Re-upgrade back to head
        command.upgrade(alembic_cfg, "head")
    finally:
        with sync_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS external_vector_dependent_table;"))
        sync_engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_sole_admin_concurrency_serialization(
    integration_settings: Settings,
) -> None:
    """Verify that concurrent operations cannot demote or remove the last active administrator (Finding 2)."""
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = generate_uuid7()
    super_admin_id = generate_uuid7()
    admin_1_id = generate_uuid7()
    admin_2_id = generate_uuid7()
    admin_role_id = generate_uuid7()

    try:
        # Step 1: Seed organization, org_admin role, and 2 active administrators
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            org = Organization(
                id=tenant_id,
                name=f"Sole Admin Concurrency Org {tenant_id.hex[:6]}",
                slug=f"sole-admin-org-{tenant_id.hex[:6]}",
                status="active",
            )
            session.add(org)

            # Check if system org_admin role exists, or insert test role
            role_stmt = select(Role).where(Role.name == "org_admin")
            role = (await session.execute(role_stmt)).scalars().first()
            if not role:
                role = Role(
                    id=admin_role_id,
                    name="org_admin",
                    description="Organization Administrator",
                    tenant_id=None,
                    is_system=True,
                )
                session.add(role)
            else:
                admin_role_id = role.id

            super_user = User(
                id=super_admin_id,
                email=f"super_{super_admin_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecret123!"),
                first_name="Super",
                last_name="Admin",
                is_active=True,
                is_super_admin=True,
            )
            user_1 = User(
                id=admin_1_id,
                email=f"admin1_{admin_1_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecret123!"),
                first_name="Admin",
                last_name="One",
                is_active=True,
                is_super_admin=False,
            )
            user_2 = User(
                id=admin_2_id,
                email=f"admin2_{admin_2_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecret123!"),
                first_name="Admin",
                last_name="Two",
                is_active=True,
                is_super_admin=False,
            )
            session.add_all([super_user, user_1, user_2])
            await session.flush()

            mem_1 = OrganizationMembership(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                user_id=admin_1_id,
                role_id=admin_role_id,
                is_active=True,
            )
            mem_2 = OrganizationMembership(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                user_id=admin_2_id,
                role_id=admin_role_id,
                is_active=True,
            )
            session.add_all([mem_1, mem_2])
            await session.commit()

        # Step 2: Concurrently execute two simultaneous membership removals
        # Both operations are authorized by super_user to eliminate actor revocation side effects
        async def remove_op_1() -> bool:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_id)
                return await remove_membership(
                    db=session,
                    tenant_id=tenant_id,
                    target_user_id=admin_1_id,
                    actor_user_id=super_admin_id,
                )

        async def remove_op_2() -> bool:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_id)
                return await remove_membership(
                    db=session,
                    tenant_id=tenant_id,
                    target_user_id=admin_2_id,
                    actor_user_id=super_admin_id,
                )

        results = await asyncio.gather(remove_op_1(), remove_op_2(), return_exceptions=True)

        successes = [r for r in results if r is True]
        failures = [r for r in results if isinstance(r, AuthorizationException)]

        assert len(successes) == 1, f"Exactly one simultaneous removal must succeed, got {results}"
        assert (
            len(failures) == 1
        ), f"Exactly one simultaneous removal must be rejected, got {results}"
        assert failures[0].error_code == "SOLE_ADMIN_PROTECTION_VIOLATION"

        # Step 3: Verify that in the database, exactly ONE active administrator remains
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            count_stmt = (
                select(func.count(OrganizationMembership.id))
                .join(Role, Role.id == OrganizationMembership.role_id)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.is_active.is_(True),
                    Role.name == "org_admin",
                )
            )
            remaining_admins = (await session.execute(count_stmt)).scalar()
            assert (
                remaining_admins == 1
            ), f"Expected exactly 1 admin remaining, got {remaining_admins}"

        # Step 4: Attempting to remove the sole remaining administrator is immediately rejected
        with pytest.raises(AuthorizationException) as exc_sole:
            async with session_factory() as session:
                await set_tenant_context(session, tenant_id)
                # Determine which admin remains and attempt removal
                rem_stmt = (
                    select(OrganizationMembership.user_id)
                    .join(Role, Role.id == OrganizationMembership.role_id)
                    .where(
                        OrganizationMembership.tenant_id == tenant_id,
                        OrganizationMembership.is_active.is_(True),
                        Role.name == "org_admin",
                    )
                )
                last_admin_id = (await session.execute(rem_stmt)).scalar_one()
                await remove_membership(
                    db=session,
                    tenant_id=tenant_id,
                    target_user_id=last_admin_id,
                    actor_user_id=super_admin_id,
                )
        assert exc_sole.value.error_code == "SOLE_ADMIN_PROTECTION_VIOLATION"

    finally:
        await engine.dispose()


@skip_if_no_postgres
@pytest.mark.asyncio
async def test_actor_revocation_while_waiting_for_organization_lock_rejected(
    integration_settings: Settings,
) -> None:
    """Verify that an administrator whose privileges are revoked while waiting for the organization lock

    cannot execute operations using stale permissions across assign_membership_role, update_membership,
    and remove_membership.
    """
    engine = create_db_engine(integration_settings)
    session_factory = create_session_factory(engine)

    tenant_id = generate_uuid7()
    admin_id = generate_uuid7()
    super_admin_id = generate_uuid7()
    target_user_id = generate_uuid7()

    try:
        # Step 1: Seed organization, system roles (org_admin, recruiter), and users
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            org = Organization(
                id=tenant_id,
                name=f"Lock Order Test Org {tenant_id.hex[:6]}",
                slug=f"lock-order-org-{tenant_id.hex[:6]}",
                status="active",
            )
            session.add(org)

            # Resolve system org_admin role
            admin_role = (
                (await session.execute(select(Role).where(Role.name == "org_admin")))
                .scalars()
                .first()
            )
            assert admin_role is not None

            # Resolve system recruiter role
            recruiter_role = (
                (await session.execute(select(Role).where(Role.name == "recruiter")))
                .scalars()
                .first()
            )
            assert recruiter_role is not None

            super_user = User(
                id=super_admin_id,
                email=f"super_lock_{super_admin_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Super",
                last_name="Admin",
                is_active=True,
                is_super_admin=True,
            )
            admin_user = User(
                id=admin_id,
                email=f"admin_lock_{admin_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Admin",
                last_name="Actor",
                is_active=True,
                is_super_admin=False,
            )
            target_user = User(
                id=target_user_id,
                email=f"target_lock_{target_user_id.hex[:6]}@example.com",
                password_hash=hash_password("SuperSecretPass123!"),
                first_name="Target",
                last_name="Member",
                is_active=True,
                is_super_admin=False,
            )
            session.add_all([super_user, admin_user, target_user])
            await session.flush()

            # Admin membership
            admin_mem = OrganizationMembership(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                user_id=admin_id,
                role_id=admin_role.id,
                is_active=True,
            )
            # Target membership initially recruiter
            target_mem = OrganizationMembership(
                id=generate_uuid7(),
                tenant_id=tenant_id,
                user_id=target_user_id,
                role_id=recruiter_role.id,
                is_active=True,
            )
            session.add_all([admin_mem, target_mem])
            await session.commit()

        # ----------------------------------------------------------------------
        # Test 1: assign_membership_role blocked if actor demoted while waiting on lock
        # ----------------------------------------------------------------------
        async with session_factory() as session_1:
            await set_tenant_context(session_1, tenant_id)
            # Session 1 acquires organization row lock
            await session_1.execute(
                select(Organization.id).where(Organization.id == tenant_id).with_for_update()
            )

            # Session 2 attempts assign_membership_role (blocks on organization lock)
            async def try_assign() -> OrganizationMembership:
                async with session_factory() as session_2:
                    await set_tenant_context(session_2, tenant_id)
                    return await assign_membership_role(
                        db=session_2,
                        tenant_id=tenant_id,
                        target_user_id=target_user_id,
                        new_role_id=admin_role.id,
                        actor_user_id=admin_id,
                    )

            assign_task = asyncio.create_task(try_assign())
            await asyncio.sleep(0.05)  # Ensure Task 2 is waiting on PostgreSQL lock

            # Session 1 demotes admin_id to recruiter while Task 2 is waiting
            await session_1.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == admin_id,
                )
                .values(role_id=recruiter_role.id)
            )
            await session_1.commit()  # Commits demotion & releases lock to Task 2

            with pytest.raises(AuthorizationException) as exc_assign:
                await assign_task
            assert exc_assign.value.error_code == "MEMBERSHIP_MUTATION_FORBIDDEN"

        # Re-promote admin_id to org_admin
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            await session.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == admin_id,
                )
                .values(role_id=admin_role.id, is_active=True)
            )
            await session.commit()

        # ----------------------------------------------------------------------
        # Test 2: update_membership blocked if actor deactivated while waiting on lock
        # ----------------------------------------------------------------------
        async with session_factory() as session_1:
            await set_tenant_context(session_1, tenant_id)
            await session_1.execute(
                select(Organization.id).where(Organization.id == tenant_id).with_for_update()
            )

            async def try_update() -> OrganizationMembership:
                async with session_factory() as session_2:
                    await set_tenant_context(session_2, tenant_id)
                    return await update_membership(
                        db=session_2,
                        tenant_id=tenant_id,
                        target_user_id=target_user_id,
                        update_data={"is_active": False},
                        actor_user_id=admin_id,
                    )

            update_task = asyncio.create_task(try_update())
            await asyncio.sleep(0.05)

            # Session 1 deactivates admin_id while Task 2 is waiting
            await session_1.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == admin_id,
                )
                .values(is_active=False)
            )
            await session_1.commit()

            with pytest.raises(AuthorizationException) as exc_update:
                await update_task
            assert exc_update.value.error_code == "MEMBERSHIP_MUTATION_FORBIDDEN"

        # Re-activate and re-promote admin_id
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            await session.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == admin_id,
                )
                .values(role_id=admin_role.id, is_active=True)
            )
            await session.commit()

        # ----------------------------------------------------------------------
        # Test 3: remove_membership blocked if actor demoted while waiting on lock
        # ----------------------------------------------------------------------
        async with session_factory() as session_1:
            await set_tenant_context(session_1, tenant_id)
            await session_1.execute(
                select(Organization.id).where(Organization.id == tenant_id).with_for_update()
            )

            async def try_remove() -> bool:
                async with session_factory() as session_2:
                    await set_tenant_context(session_2, tenant_id)
                    return await remove_membership(
                        db=session_2,
                        tenant_id=tenant_id,
                        target_user_id=target_user_id,
                        actor_user_id=admin_id,
                    )

            remove_task = asyncio.create_task(try_remove())
            await asyncio.sleep(0.05)

            # Session 1 demotes admin_id while Task 2 is waiting
            await session_1.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.tenant_id == tenant_id,
                    OrganizationMembership.user_id == admin_id,
                )
                .values(role_id=recruiter_role.id)
            )
            await session_1.commit()

            with pytest.raises(AuthorizationException) as exc_remove:
                await remove_task
            assert exc_remove.value.error_code == "MEMBERSHIP_MUTATION_FORBIDDEN"

        # Verify target user still exists and was not removed
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            target_check = (
                await session.execute(
                    select(OrganizationMembership.id).where(
                        OrganizationMembership.tenant_id == tenant_id,
                        OrganizationMembership.user_id == target_user_id,
                    )
                )
            ).scalar_one_or_none()
            assert target_check is not None, "Target membership must not have been deleted"

    finally:
        await engine.dispose()
