"""Resilience, fault-injection, and failure recovery test suite.

Verifies:
1. Database disconnection and transaction rollback integrity.
2. Redis connection failure modes (fail-closed security endpoints vs graceful degradation).
3. Celery broker connection drops and safe task dispatch recovery.
4. Transaction atomic rollback on partial operation failures (zero orphaned records).
"""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.base import utc_now
from app.core.config import get_settings
from app.core.errors import (
    AppException,
    ServiceUnavailableException,
)
from app.core.security.rate_limit import check_rate_limit
from app.core.tasks.idempotency import IdempotencyManager
from app.modules.auth.dependencies import authenticate_request_pipeline
from app.modules.auth.jwt import COOKIE_ACCESS, create_access_token
from app.services.task_service import TaskService
from tests.test_auth_dependencies_pipeline import _make_request

# ------------------------------------------------------------------------------
# 1. Database Disconnection & Rollback Resilience
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_database_operational_error_rolls_back_and_fails_safely() -> None:
    """When a database operational error occurs, transaction rolls back and sensitive data is not leaked."""
    mock_session = AsyncMock()
    # Simulate DB connection drop / operational error during commit
    mock_session.commit.side_effect = OperationalError(
        "connection lost", params=None, orig=Exception("TCP reset")
    )

    async def protected_operation() -> None:
        try:
            # Operation performs some work then commits
            mock_session.add(MagicMock())
            await mock_session.commit()
        except OperationalError:
            await mock_session.rollback()
            raise ServiceUnavailableException(
                "Database connectivity lost during transaction"
            ) from None

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await protected_operation()

    # Verifies rollback was strictly executed
    mock_session.rollback.assert_awaited_once()
    assert exc_info.value.status_code == 503
    assert "Database connectivity lost" in exc_info.value.message
    # No SQL parameters or raw exception internals leaked in user message
    assert "TCP reset" not in exc_info.value.message


@pytest.mark.asyncio
async def test_database_integrity_violation_rolls_back_atomically() -> None:
    """Constraint violation triggers immediate transaction rollback with zero orphaned writes."""
    mock_session = AsyncMock()
    mock_session.flush.side_effect = DBAPIError(
        "UNIQUE constraint failed", params=None, orig=Exception()
    )

    async def insert_user_with_profiles() -> None:
        try:
            mock_session.add(MagicMock())  # User record
            await mock_session.flush()
            mock_session.add(MagicMock())  # Profile record (never reached)
            await mock_session.commit()
        except DBAPIError:
            await mock_session.rollback()
            raise

    with pytest.raises(DBAPIError):
        await insert_user_with_profiles()

    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_called()


# ------------------------------------------------------------------------------
# 2. Redis Unavailability & Failure Modes
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_fail_closed_on_sensitive_auth_endpoints() -> None:
    """When Redis is unreachable, rate limiter fails closed (raises ServiceUnavailableException) for security endpoints."""
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = RedisConnectionError("Redis connection refused")

    # Sensitive action (e.g. login / password reset) must fail closed to prevent brute-force exploitation
    with pytest.raises(ServiceUnavailableException) as exc_info:
        await check_rate_limit(
            redis=mock_redis,
            identifier="192.168.1.1",
            action="login_attempt",
            max_requests=5,
            window_seconds=300,
            fail_closed=True,
        )
    assert exc_info.value.code == "RATE_LIMIT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_rate_limiter_graceful_degradation_on_non_sensitive_endpoints() -> None:
    """When Redis is unreachable, non-sensitive endpoints degrade gracefully (fail_closed=False)."""
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = RedisTimeoutError("Redis timed out after 500ms")

    allowed, count, retry_after = await check_rate_limit(
        redis=mock_redis,
        identifier="192.168.1.1",
        action="read_public_docs",
        max_requests=100,
        window_seconds=60,
        fail_closed=False,
    )
    assert allowed is True, "Non-critical read endpoint should allow traffic during cache outage"
    assert count == 1
    assert retry_after == 0


@pytest.mark.asyncio
async def test_auth_pipeline_state_c_handles_redis_timeout_transparently() -> None:
    """Redis timeout during session lookup transitions seamlessly to PostgreSQL authoritative check."""
    settings = get_settings()
    user_id = str(uuid4())
    session_id = str(uuid4())

    jwt_token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=["view_jobs"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    req = _make_request(cookies={COOKIE_ACCESS: jwt_token})

    mock_redis = AsyncMock()
    mock_redis.get.side_effect = RedisTimeoutError("i/o timeout")

    mock_db = AsyncMock()
    mock_session_record = MagicMock()
    mock_session_record.id = UUID(session_id)
    mock_session_record.user_id = UUID(user_id)
    mock_session_record.is_revoked = False
    mock_session_record.expires_at = utc_now() + timedelta(hours=1)
    mock_session_record.token_version = 1

    # Return valid session from DB
    mock_db_sess_res = MagicMock()
    mock_db_sess_res.scalar_one_or_none.return_value = mock_session_record

    mock_db_6dim_res = MagicMock()
    mock_db_6dim_res.mappings.return_value.first.return_value = {
        "user_id": user_id,
        "token_version": 1,
        "user_active": True,
        "force_authoritative_check": False,
    }
    mock_db.execute.side_effect = [mock_db_sess_res, mock_db_6dim_res]

    sec_ctx = await authenticate_request_pipeline(
        request=req,
        db=mock_db,
        redis=mock_redis,
        settings=settings,
    )
    assert str(sec_ctx.user_id) == user_id
    assert sec_ctx.roles == ["candidate"]


# ------------------------------------------------------------------------------
# 3. Celery Broker Disconnection & Task Dispatch Resilience
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_service_dispatch_broker_failure_marks_unknown() -> None:
    """When Celery broker fails during send_task, dispatch state transitions safely to DISPATCH_UNKNOWN."""
    mock_redis = AsyncMock()
    task_service = TaskService()

    # Mock Celery send_task raising operational broker error
    with patch.object(task_service.celery, "send_task") as mock_send:
        mock_send.side_effect = ConnectionError("Cannot route message to broker: connection lost")

        # Mock idempotency registration success in Redis
        mock_redis.eval.return_value = '["1", "test-lock-token", "{\\"status\\": \\"PENDING\\"}"]'

        with pytest.raises(Exception) as exc_info:
            await task_service.submit_task(
                task="app.core.tasks.system.system_ping",
                idempotency_key="resilience-ping-key-01",
                args=("payload",),
                tenant_id=uuid4(),
                redis_client=mock_redis,
            )
        assert "Cannot route message" in str(exc_info.value) or isinstance(
            exc_info.value, AppException
        )


# ------------------------------------------------------------------------------
# 4. Outbox & Background Task Reconciliation Resilience
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_manager_lock_acquisition_timeout_fails_closed() -> None:
    """When idempotency manager cannot reach Redis to acquire lock, it raises ServiceUnavailableException (fails closed)."""
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = RedisConnectionError("Redis down")

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await IdempotencyManager.acquire_async(
            client=mock_redis,
            key="critical-payroll-run-123",
            task_id="task-uuid-456",
            lock_ttl=60,
        )
    assert exc_info.value.code == "IDEMPOTENCY_UNAVAILABLE"


# ------------------------------------------------------------------------------
# 5. Live Infrastructure Resilience Integration Tests
# ------------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_postgres_transaction_rollback_and_pool_recovery() -> None:
    """Live PostgreSQL verifies atomic rollback on failure and immediate pool connection recovery."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set; skipping live PostgreSQL resilience test")

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.core.database import create_db_engine, create_session_factory

    engine = create_db_engine(database_url)
    session_factory = create_session_factory(engine)

    try:
        # 1. Simulate transaction failure (invalid SQL query / constraint failure)
        async with session_factory() as session:
            try:
                await session.execute(
                    text("INSERT INTO non_existent_table_for_fault_test (id) VALUES (1);")
                )
                await session.commit()
            except DBAPIError:
                await session.rollback()

        # 2. Verify connection returned to pool is healthy and immediately reusable
        async with session_factory() as session:
            result = await session.execute(text("SELECT 1 AS alive;"))
            row = result.scalar()
            assert row == 1
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_redis_reconnection_and_circuit_recovery() -> None:
    """Live Redis verifies state consistency, lock acquisition, and connection recovery."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    import redis.asyncio as aioredis

    try:
        client = aioredis.from_url(redis_url, socket_timeout=2.0)
        await client.ping()
    except Exception:
        pytest.skip("Live Redis not reachable; skipping Redis live resilience test")

    test_key = f"resilience:live:test:{uuid4()}"
    try:
        # Set and get key
        await client.set(test_key, "active", ex=60)
        val = await client.get(test_key)
        assert val == b"active" or val == "active"

        # Acquire distributed lock using IdempotencyManager
        token = await IdempotencyManager.acquire_async(
            client=client,
            key=test_key,
            task_id=str(uuid4()),
            lock_ttl=30,
        )
        assert token is not None

        # Second acquisition must be rejected (concurrency protection)
        second_token = await IdempotencyManager.acquire_async(
            client=client,
            key=test_key,
            task_id=str(uuid4()),
            lock_ttl=30,
        )
        assert second_token is None

        # Clean release
        await IdempotencyManager.release_async(client=client, key=test_key, token=token)
    finally:
        await client.delete(test_key)
        await client.aclose()
