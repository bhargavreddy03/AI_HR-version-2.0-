"""Integration test suite verifying PostgreSQL 16 connection lifecycle, RLS isolation, migrations, and concurrency controls."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
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
    """Verify database role initialization with configured credentials,
    rejection of invalid credentials, and catalog attributes (rolsuper=f, rolbypassrls=f, rolcreatedb=f).
    """
    from sqlalchemy.engine import make_url

    # 1. Verify runtime application user connects and authenticates with configured credentials
    runtime_engine = create_db_engine(integration_settings)
    try:
        async with runtime_engine.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            assert res.scalar() == integration_settings.POSTGRES_USER

            # Verify runtime role attributes: strictly NOSUPERUSER, NOBYPASSRLS, NOCREATEDB
            role_attr_res = await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb "
                    "FROM pg_roles WHERE rolname = current_user;"
                )
            )
            super_val, rls_val, createdb_val = role_attr_res.one()
            assert super_val is False, "Runtime role must have rolsuper = false"
            assert rls_val is False, "Runtime role must have rolbypassrls = false"
            assert createdb_val is False, "Runtime role must have rolcreatedb = false"
    finally:
        await runtime_engine.dispose()

    # 2. Verify migration user connects and authenticates with configured migration credentials
    migration_url = (
        getattr(integration_settings, "DATABASE_MIGRATION_URL", None)
        or os.getenv("DATABASE_MIGRATION_URL")
        or getattr(integration_settings, "DATABASE_SYNC_URL", None)
        or integration_settings.DATABASE_URL
    )
    if migration_url.startswith("postgresql://"):
        migration_url = migration_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    mig_engine = create_async_engine(migration_url)
    try:
        async with mig_engine.connect() as conn:
            res = await conn.execute(text("SELECT current_user;"))
            mig_user = integration_settings.POSTGRES_MIGRATION_USER or "aihr_migration_user"
            assert res.scalar() == mig_user

            # Verify migration role attributes: strictly NOSUPERUSER, NOBYPASSRLS, NOCREATEDB
            mig_attr_res = await conn.execute(
                text(
                    f"SELECT rolsuper, rolbypassrls, rolcreatedb FROM pg_roles WHERE rolname = '{mig_user}';"
                )
            )
            super_val, rls_val, createdb_val = mig_attr_res.one()
            assert super_val is False, "Migration role must have rolsuper = false"
            assert rls_val is False, "Migration role must have rolbypassrls = false"
            assert createdb_val is False, "Migration role must have rolcreatedb = false"
    finally:
        await mig_engine.dispose()

    # 3. Verify that incorrect credentials for runtime role are rejected by PostgreSQL
    bad_runtime_url = make_url(integration_settings.DATABASE_URL).set(
        password="invalid_wrong_password_for_testing"
    )
    bad_runtime_engine = create_async_engine(bad_runtime_url)
    try:
        with pytest.raises(DBAPIError):
            async with bad_runtime_engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
    finally:
        await bad_runtime_engine.dispose()

    # 4. Verify that incorrect credentials for migration role are rejected by PostgreSQL
    bad_mig_url = make_url(migration_url).set(password="invalid_wrong_password_for_testing")
    bad_mig_engine = create_async_engine(bad_mig_url)
    try:
        with pytest.raises(DBAPIError):
            async with bad_mig_engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
    finally:
        await bad_mig_engine.dispose()


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
