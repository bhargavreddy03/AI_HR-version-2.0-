"""Integration tests verifying Celery execution with live Redis broker, result backend, and real worker process.

Covers complete end-to-end authenticated task dispatch, idempotency lifecycle, lock ownership,
and tenant boundary protection under live Redis and worker conditions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis
from celery.result import AsyncResult
from httpx import ASGITransport, AsyncClient

from app.core.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import ServiceUnavailableException
from app.core.redis import create_redis_client, get_sync_redis_client
from app.core.security import SecurityContext
from app.core.tasks.idempotency import (
    LUA_RECONCILE_DISPATCH,
    IdempotencyManager,
    format_scoped_key,
)
from app.core.tasks.system import system_ping
from app.main import create_application
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.documents.tasks import parse_document
from app.services.task_service import TaskService

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")


def is_redis_reachable() -> bool:
    """Synchronous check if Redis is live and accepting commands."""
    try:
        r = redis.Redis.from_url(REDIS_URL, socket_timeout=2.0)
        return bool(r.ping())
    except Exception:
        return False


REDIS_AVAILABLE = is_redis_reachable()
skip_if_no_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason=f"Redis service is unavailable at {REDIS_URL}",
)

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def live_celery_worker():
    """Start an actual live Celery worker subprocess connected to test Redis."""
    env = os.environ.copy()
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.worker.celery_app",
            "worker",
            "--loglevel=info",
            "--pool=solo",
            "--concurrency=1",
            "-Q",
            "default,document_processing",
        ],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ready = False
    start_time = time.time()
    while time.time() - start_time < 12.0:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"Celery worker exited unexpectedly (code {proc.returncode}):\n{stderr.decode()}"
            )
        try:
            inspect_res = celery_app.control.ping(timeout=0.5)
            if inspect_res:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.4)

    if not ready:
        proc.kill()
        proc.wait()
        raise TimeoutError("Celery worker did not respond to ping within 12 seconds")

    yield proc

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_broker_and_result_backend_task_execution(live_celery_worker: Any) -> None:
    """Verify that a real Celery worker receives, executes, and stores the task result via live Redis."""
    res = system_ping.apply_async(args=("live-redis-test",), queue="default")
    assert res.id is not None

    result = res.get(timeout=10.0)
    assert res.successful() is True
    assert result["status"] == "pong"
    assert result["message"] == "live-redis-test"

    ar = AsyncResult(res.id, app=celery_app)
    assert ar.state == "SUCCESS"
    assert ar.result["status"] == "pong"
    assert ar.result["message"] == "live-redis-test"


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_queue_routing_lists() -> None:
    """Verify tasks are enqueued into the exact Redis queue lists mapped in routing."""
    r_broker = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)

    initial_doc_len = r_broker.llen("document_processing")

    async_doc = parse_document.apply_async(
        kwargs={
            "document_id": "live-doc-123",
            "tenant_id": "tenant-live-456",
        },
        queue="document_processing",
    )
    assert async_doc.id is not None

    new_doc_len = r_broker.llen("document_processing")
    assert new_doc_len >= initial_doc_len + 1

    raw_msg = r_broker.rpop("document_processing")
    assert raw_msg is not None


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_strict_lock_ownership_rejections() -> None:
    """Verify strict rejection of missing tokens, stale tokens, and expired locks."""
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    test_key = "strict-lock-test-" + uuid.uuid4().hex
    manager.force_delete(test_key)

    # 1. Missing token on acquire -> rejects complete / fail / release
    acquired, lock_token, _ = manager.acquire(test_key, task_id="task-1", lock_ttl=60)
    assert acquired is True
    assert lock_token is not None

    # Missing token rejected
    assert (
        manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token=None) is False
    )
    assert manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token="") is False
    assert manager.fail(test_key, error="err", task_id="task-1", lock_token=None) is False
    assert manager.release(test_key, lock_token=None) is False

    # Stale token rejected
    assert (
        manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token="stale-tok")
        is False
    )
    assert manager.fail(test_key, error="err", task_id="task-1", lock_token="stale-tok") is False
    assert manager.release(test_key, lock_token="stale-tok") is False

    # Legitimate complete succeeds
    assert (
        manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token=lock_token)
        is True
    )

    # After completion, stored lock_token is null -> any complete/fail/release attempt rejected
    assert (
        manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token=lock_token)
        is False
    )
    assert manager.fail(test_key, error="err", task_id="task-1", lock_token=lock_token) is False
    assert manager.release(test_key, lock_token=lock_token) is False

    # Expired / non-existent key rejected
    manager.force_delete(test_key)
    assert (
        manager.complete(test_key, result={"ok": True}, task_id="task-1", lock_token=lock_token)
        is False
    )


@pytest.mark.integration
@skip_if_no_redis
@pytest.mark.asyncio
async def test_end_to_end_authenticated_idempotent_task_execution(live_celery_worker: Any) -> None:
    """Verify complete end-to-end task execution lifecycle through live Redis and Celery worker.

    Proves:
    1. Authenticated API submission with Idempotency-Key.
    2. Real Celery worker receives, executes, and stores the task result.
    3. Duplicate API submission returns original task ID without redispatching.
    4. Task executes only once.
    5. Authenticated result retrieval succeeds for owning tenant.
    6. Cross-tenant access is rejected with 403 Forbidden.
    """
    app = create_application()
    redis_client = create_redis_client(Settings())
    app.state.redis_client = redis_client

    auth_a = SecurityContext(
        user_id=USER_A,
        session_id=uuid.uuid4(),
        tenant_id=TENANT_A,
        roles=["recruiter"],
        permissions=["recruiter:read", "recruiter:write"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )
    auth_b = SecurityContext(
        user_id=USER_B,
        session_id=uuid.uuid4(),
        tenant_id=TENANT_B,
        roles=["recruiter"],
        permissions=["recruiter:read", "recruiter:write"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )

    idem_key = "e2e-idem-" + uuid.uuid4().hex
    app.dependency_overrides[require_authenticated_user] = lambda: auth_a

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Step 1: Submit initial task with Idempotency-Key
        res1 = await ac.post(
            "/api/v1/tasks/system/ping",
            json={"message": "e2e-payload"},
            headers={"Idempotency-Key": idem_key},
        )
        assert res1.status_code == 202
        data1 = res1.json()
        task_id = data1["task_id"]
        assert data1["duplicate"] is False
        assert data1["status"] == "PENDING"

        # Step 2: Submit duplicate task with same Idempotency-Key
        res2 = await ac.post(
            "/api/v1/tasks/system/ping",
            json={"message": "e2e-payload"},
            headers={"Idempotency-Key": idem_key},
        )
        assert res2.status_code == 202
        data2 = res2.json()
        assert data2["task_id"] == task_id
        assert data2["duplicate"] is True

        # Step 3: Await real worker execution via Celery AsyncResult
        ar = AsyncResult(task_id, app=celery_app)
        start_time = time.time()
        while time.time() - start_time < 12.0:
            if ar.ready():
                break
            time.sleep(0.3)

        assert ar.ready() is True
        assert ar.successful() is True
        result_payload = ar.result
        assert result_payload["status"] == "pong"
        assert result_payload["message"] == "e2e-payload"
        assert result_payload["idempotency_key"] == idem_key

        # Step 4: Authenticated status query for Tenant A
        res_status = await ac.get(f"/api/v1/tasks/{task_id}/status")
        assert res_status.status_code == 200
        status_data = res_status.json()
        assert status_data["task_id"] == task_id
        assert status_data["status"] == "SUCCESS"
        assert status_data["ready"] is True
        assert status_data["successful"] is True

        # Step 5: Authenticated result retrieval for Tenant A
        res_result = await ac.get(f"/api/v1/tasks/{task_id}/result")
        assert res_result.status_code == 200
        result_data = res_result.json()
        assert result_data["result"]["status"] == "pong"
        assert result_data["result"]["message"] == "e2e-payload"

        # Step 6: Cross-tenant isolation verification (Tenant B must be rejected)
        app.dependency_overrides[require_authenticated_user] = lambda: auth_b
        res_b_status = await ac.get(f"/api/v1/tasks/{task_id}/status")
        assert res_b_status.status_code == 403

        res_b_result = await ac.get(f"/api/v1/tasks/{task_id}/result")
        assert res_b_result.status_code == 403

        # Step 7: Cross-tenant idempotency isolation (Tenant B submitting with same key creates independent task)
        res_b_idem = await ac.post(
            "/api/v1/tasks/system/ping",
            json={"message": "tenant-b-payload"},
            headers={"Idempotency-Key": idem_key},
        )
        assert res_b_idem.status_code == 202
        data_b = res_b_idem.json()
        assert data_b["duplicate"] is False
        assert data_b["task_id"] != task_id

    await redis_client.aclose()


@pytest.mark.asyncio
async def test_redis_failure_rejects_idempotent_submission() -> None:
    """Verify that if an idempotency key is supplied and Redis fails, submission is rejected."""
    service = TaskService()
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = redis.ConnectionError("Redis connection lost")

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await service.submit_task(
            task=system_ping,
            args=("test",),
            idempotency_key="key-fail",
            redis_client=mock_redis,
        )

    assert "Idempotency service unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_dispatch_failure_records_recoverable_dispatch_unknown() -> None:
    """Verify that when task dispatch fails, DISPATCH_UNKNOWN state is recorded to prevent duplicate execution."""
    service = TaskService()
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = [1, "{}"]  # registration succeeded

    with patch.object(
        system_ping, "apply_async", side_effect=RuntimeError("Broker transport down")
    ):
        with pytest.raises(ServiceUnavailableException) as exc_info:
            await service.submit_task(
                task=system_ping,
                args=("test",),
                idempotency_key="key-dispatch-unknown",
                tenant_id=TENANT_A,
                redis_client=mock_redis,
            )

    assert "Task broker unavailable" in str(exc_info.value)
    # DISPATCH_UNKNOWN state recorded via Lua script to preserve record for reconciliation
    assert mock_redis.eval.call_count == 2
    second_eval = mock_redis.eval.call_args_list[1]
    assert "DISPATCH_UNKNOWN" in str(second_eval) or "LUA_RECORD_DISPATCH_UNKNOWN" in str(
        second_eval
    )
    # Ensure idempotency key was NOT deleted
    for delete_call in mock_redis.delete.call_args_list:
        assert "key-dispatch-unknown" not in str(delete_call)


@pytest.mark.integration
@skip_if_no_redis
@pytest.mark.asyncio
async def test_live_redis_dispatch_unknown_preserves_completed_and_active_states() -> None:
    """FINDING 3: Verify live Redis Lua script rejects DISPATCH_UNKNOWN when task already COMPLETED or PROCESSING."""
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    async_redis = create_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    test_key = "live-preserve-test-" + uuid.uuid4().hex
    task_id = "task-" + uuid.uuid4().hex

    try:
        # 1. Register PENDING submission
        reg_ok, _ = await IdempotencyManager.register_submission_async(
            client=async_redis,
            key=test_key,
            task_id=task_id,
            tenant_id=TENANT_A,
        )
        assert reg_ok is True

        # 2. Worker acquires lock (state becomes PROCESSING)
        acquired, lock_token, _ = manager.acquire(test_key, task_id=task_id, lock_ttl=60)
        assert acquired is True
        assert lock_token is not None

        # Verify: DISPATCH_UNKNOWN is rejected while PROCESSING with active lock token
        rec_ok, rec_reason, _ = await IdempotencyManager.record_dispatch_unknown_async(
            client=async_redis,
            key=test_key,
            expected_task_id=task_id,
            error_msg="Simulated broker timeout",
        )
        assert rec_ok is False
        assert rec_reason in ("IMMUTABLE_STATE_PROCESSING", "ACTIVE_LOCK_PRESENT")

        # 3. Worker completes task with result
        completed = manager.complete(
            key=test_key,
            result={"status": "completed_payload", "value": 42},
            task_id=task_id,
            lock_token=lock_token,
        )
        assert completed is True

        # Verify: DISPATCH_UNKNOWN is rejected after COMPLETED, preserving result
        rec_ok2, rec_reason2, rec_data2 = await IdempotencyManager.record_dispatch_unknown_async(
            client=async_redis,
            key=test_key,
            expected_task_id=task_id,
            error_msg="Late publisher timeout",
        )
        assert rec_ok2 is False
        assert rec_reason2 == "IMMUTABLE_STATE_COMPLETED"
        assert rec_data2 is not None
        assert rec_data2["status"] == "COMPLETED"
        assert rec_data2["result"]["value"] == 42

        # Verify data in Redis is still COMPLETED
        final_data = await IdempotencyManager.get_async(async_redis, test_key)
        assert final_data is not None
        assert final_data["status"] == "COMPLETED"
        assert final_data["result"]["value"] == 42
    finally:
        manager.force_delete(test_key)
        await async_redis.aclose()


@pytest.mark.integration
@skip_if_no_redis
@pytest.mark.asyncio
async def test_live_redis_full_state_transition_matrix() -> None:
    """Verify complete state transition matrix under live Redis Lua atomic scripts.

    Transitions tested:
    1. PENDING -> PROCESSING -> COMPLETED (standard success)
    2. PENDING -> PROCESSING -> FAILED (permanent failure, fails closed)
    3. PENDING -> PROCESSING -> (Transient error release) -> PENDING -> re-acquire -> COMPLETED
    4. PENDING -> DISPATCH_UNKNOWN -> (worker acquires) -> PROCESSING -> COMPLETED
    5. PENDING -> DISPATCH_UNKNOWN -> (API reconciles) -> PENDING -> PROCESSING
    6. Concurrent duplicate suppression while PROCESSING.
    7. Stale ownership token rejection on renewal, completion, and failure.
    """
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    async_redis = create_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    # 1. PENDING -> PROCESSING -> COMPLETED
    k1 = "matrix-test-1-" + uuid.uuid4().hex
    t1 = "task-matrix-1"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k1, t1)
        acq, tok, _ = manager.acquire(k1, task_id=t1, lock_ttl=60)
        assert acq is True and tok is not None
        assert manager.complete(k1, {"result": 1}, task_id=t1, lock_token=tok) is True
        d1 = await IdempotencyManager.get_async(async_redis, k1)
        assert d1 is not None and d1["status"] == "COMPLETED"
    finally:
        manager.force_delete(k1)

    # 2. PENDING -> PROCESSING -> FAILED
    k2 = "matrix-test-2-" + uuid.uuid4().hex
    t2 = "task-matrix-2"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k2, t2)
        acq, tok, _ = manager.acquire(k2, task_id=t2, lock_ttl=60)
        assert acq is True and tok is not None
        assert manager.fail(k2, "Permanent parse error", task_id=t2, lock_token=tok) is True
        d2 = await IdempotencyManager.get_async(async_redis, k2)
        assert d2 is not None and d2["status"] == "FAILED"
        # FAILED state must fail closed on subsequent acquire attempts
        acq_fail, tok_fail, existing_fail = manager.acquire(k2, task_id=t2, lock_ttl=60)
        assert acq_fail is False
        assert tok_fail is None
        assert existing_fail is not None and existing_fail["status"] == "FAILED"
    finally:
        manager.force_delete(k2)

    # 3. PENDING -> PROCESSING -> release (transient) -> PENDING -> acquire -> COMPLETED
    k3 = "matrix-test-3-" + uuid.uuid4().hex
    t3 = "task-matrix-3"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k3, t3)
        acq, tok, _ = manager.acquire(k3, task_id=t3, lock_ttl=60)
        assert acq is True and tok is not None
        # Simulate transient error: release lock back to PENDING
        assert manager.release(k3, lock_token=tok, pending_ttl=360) is True
        d3_rel = await IdempotencyManager.get_async(async_redis, k3)
        assert d3_rel is not None and d3_rel["status"] == "PENDING"
        # Retry worker acquires lock again with new token
        acq_retry, tok_retry, _ = manager.acquire(k3, task_id=t3, lock_ttl=60)
        assert acq_retry is True and tok_retry is not None
        assert manager.complete(k3, {"retry": "success"}, task_id=t3, lock_token=tok_retry) is True
        d3_done = await IdempotencyManager.get_async(async_redis, k3)
        assert d3_done is not None and d3_done["status"] == "COMPLETED"
    finally:
        manager.force_delete(k3)

    # 4. PENDING -> DISPATCH_UNKNOWN -> worker acquires -> PROCESSING -> COMPLETED
    k4 = "matrix-test-4-" + uuid.uuid4().hex
    t4 = "task-matrix-4"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k4, t4)
        rec_ok, _, _ = await IdempotencyManager.record_dispatch_unknown_async(
            async_redis, k4, expected_task_id=t4, error_msg="Network blip during publish"
        )
        assert rec_ok is True
        # Matching task acquires from DISPATCH_UNKNOWN
        acq4, tok4, _ = manager.acquire(k4, task_id=t4, lock_ttl=60)
        assert acq4 is True and tok4 is not None
        assert manager.complete(k4, {"recovered": True}, task_id=t4, lock_token=tok4) is True
        d4 = await IdempotencyManager.get_async(async_redis, k4)
        assert d4 is not None and d4["status"] == "COMPLETED"
    finally:
        manager.force_delete(k4)

    # 5. PENDING -> DISPATCH_UNKNOWN -> API reconciles -> PENDING -> PROCESSING
    k5 = "matrix-test-5-" + uuid.uuid4().hex
    t5 = "task-matrix-5"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k5, t5)
        await IdempotencyManager.record_dispatch_unknown_async(
            async_redis, k5, expected_task_id=t5, error_msg="Ambiguous publish"
        )
        # API reconciliation resets to PENDING
        rec5_ok, _, _ = await IdempotencyManager.reconcile_dispatch_async(
            async_redis, k5, expected_task_id=t5, new_status="PENDING", ttl=360
        )
        assert rec5_ok is True
        d5_rec = await IdempotencyManager.get_async(async_redis, k5)
        assert d5_rec is not None and d5_rec["status"] == "PENDING"
        # Worker now acquires from reconciled PENDING
        acq5, tok5, _ = manager.acquire(k5, task_id=t5, lock_ttl=60)
        assert acq5 is True and tok5 is not None
    finally:
        manager.force_delete(k5)

    # 6. Concurrent duplicate suppression while PROCESSING
    k6 = "matrix-test-6-" + uuid.uuid4().hex
    t6 = "task-matrix-6"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k6, t6)
        acq6_1, tok6_1, _ = manager.acquire(k6, task_id=t6, lock_ttl=60)
        assert acq6_1 is True and tok6_1 is not None
        # Concurrent worker delivery attempt with same or different task_id fails
        acq6_2, tok6_2, data6_2 = manager.acquire(k6, task_id="task-matrix-6-dup", lock_ttl=60)
        assert acq6_2 is False
        assert tok6_2 is None
        assert data6_2 is not None and data6_2["status"] == "PROCESSING"
    finally:
        manager.force_delete(k6)

    # 7. Stale token rejection on renew, complete, and fail
    k7 = "matrix-test-7-" + uuid.uuid4().hex
    t7 = "task-matrix-7"
    try:
        await IdempotencyManager.register_submission_async(async_redis, k7, t7)
        acq7, legitimate_tok, _ = manager.acquire(k7, task_id=t7, lock_ttl=60)
        assert acq7 is True and legitimate_tok is not None

        # Renewal with stale token rejected
        renew_ok, renew_reason = manager.renew_with_reason(k7, "stale-tok-123", extend_ttl=60)
        assert renew_ok is False
        assert renew_reason == "TOKEN_MISMATCH"

        # Complete with stale token rejected
        assert manager.complete(k7, {"ok": False}, task_id=t7, lock_token="stale-tok-123") is False

        # Fail with stale token rejected
        assert manager.fail(k7, "Err", task_id=t7, lock_token="stale-tok-123") is False

        # Legitimate complete succeeds
        assert manager.complete(k7, {"ok": True}, task_id=t7, lock_token=legitimate_tok) is True
    finally:
        manager.force_delete(k7)
        await async_redis.aclose()


@pytest.mark.integration
@skip_if_no_redis
@pytest.mark.asyncio
async def test_live_redis_started_race_preserves_dispatch_unknown_and_worker_completes() -> None:
    """DEFECT 1 & 2 LIVE REDIS TEST:

    1. Celery reports STARTED before worker acquires lock; API retry preserves DISPATCH_UNKNOWN in live Redis.
    2. Worker subsequently acquires lock from DISPATCH_UNKNOWN and completes successfully.
    3. Live Lua rejects mismatched task ID and 'standalone' task ID against existing record.
    4. Live Lua rejects reconciliation with non-PENDING target status.
    """
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    async_redis = create_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    test_key = "live-started-race-" + uuid.uuid4().hex
    task_id = "live-task-" + uuid.uuid4().hex
    scoped_key = format_scoped_key(key=test_key, tenant_id=TENANT_A, task_type="system_ping")

    try:
        # Step 1: Initial submission registered in live Redis
        reg_ok, _ = await IdempotencyManager.register_submission_async(
            client=async_redis,
            key=scoped_key,
            task_id=task_id,
            tenant_id=TENANT_A,
            task_type="system_ping",
        )
        assert reg_ok is True

        # Step 2: Dispatch encountered broker uncertainty -> records DISPATCH_UNKNOWN
        rec_ok, _, _ = await IdempotencyManager.record_dispatch_unknown_async(
            client=async_redis,
            key=scoped_key,
            expected_task_id=task_id,
            error_msg="Temporary broker connection glitch",
        )
        assert rec_ok is True
        d_unknown = await IdempotencyManager.get_async(async_redis, scoped_key)
        assert d_unknown is not None and d_unknown["status"] == "DISPATCH_UNKNOWN"

        # Step 3: API client retries while Celery reports STARTED
        service = TaskService()
        with patch("app.services.task_service.AsyncResult") as mock_ar_cls:
            mock_ar = MagicMock()
            mock_ar.state = "STARTED"
            mock_ar_cls.return_value = mock_ar

            submit_res = await service.submit_task(
                task=system_ping,
                args=("race-check",),
                idempotency_key=test_key,
                tenant_id=TENANT_A,
                redis_client=async_redis,
            )

            assert submit_res.duplicate is True
            assert submit_res.task_id == task_id
            assert submit_res.status == "STARTED"

        # Step 4: Verify live Redis record was NOT corrupted to "STARTED", remains DISPATCH_UNKNOWN
        d_check = await IdempotencyManager.get_async(async_redis, scoped_key)
        assert d_check is not None
        assert d_check["status"] == "DISPATCH_UNKNOWN"
        assert d_check["task_id"] == task_id

        # Step 5: Test 4 & 5 - Verify mismatched task_id and 'standalone' cannot acquire
        acq_mismatch, _, _ = manager.acquire(scoped_key, task_id="intruder-task-id", lock_ttl=60)
        assert acq_mismatch is False

        acq_standalone, _, _ = manager.acquire(scoped_key, task_id="standalone", lock_ttl=60)
        assert acq_standalone is False

        # Step 6: Test 3 - Verify live Lua rejects reconciliation with non-PENDING status
        lua_invalid_res = await async_redis.eval(
            LUA_RECONCILE_DISPATCH,
            1,
            scoped_key,
            task_id,
            "STARTED",
            "360",
            "now",
        )
        assert lua_invalid_res[0] == 0
        assert lua_invalid_res[1] == "INVALID_TARGET_STATUS"

        # Step 7: Worker arrives with matching task_id and acquires lock from DISPATCH_UNKNOWN
        acq_worker, lock_token, _ = manager.acquire(scoped_key, task_id=task_id, lock_ttl=60)
        assert acq_worker is True
        assert lock_token is not None

        # Step 8: Worker completes execution and stores result in live Redis
        completed = manager.complete(
            key=scoped_key,
            result={"status": "pong", "message": "race-check-completed"},
            task_id=task_id,
            lock_token=lock_token,
        )
        assert completed is True

        # Step 9: Verify final state is COMPLETED with intact result
        final_d = await IdempotencyManager.get_async(async_redis, scoped_key)
        assert final_d is not None
        assert final_d["status"] == "COMPLETED"
        assert final_d["result"]["message"] == "race-check-completed"

    finally:
        manager.force_delete(scoped_key)
        await async_redis.aclose()
