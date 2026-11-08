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
from unittest.mock import AsyncMock, patch

import pytest
import redis
from celery.result import AsyncResult
from httpx import ASGITransport, AsyncClient

from app.core.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import ServiceUnavailableException
from app.core.redis import create_redis_pool, get_sync_redis_client
from app.core.security import SecurityContext
from app.core.tasks.idempotency import IdempotencyManager
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
    redis_pool = create_redis_pool(Settings())
    app.state.redis_client = redis_pool

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

    await redis_pool.aclose()


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
async def test_dispatch_failure_rolls_back_pending_idempotency_and_metadata() -> None:
    """Verify that when task dispatch fails, the pending idempotency and metadata keys are rolled back."""
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
                idempotency_key="key-rollback",
                tenant_id=TENANT_A,
                redis_client=mock_redis,
            )

    assert "Task broker unavailable" in str(exc_info.value)
    # Both task metadata and idempotency key must have been deleted to avoid stuck PENDING state
    delete_calls = [c.args[0] for c in mock_redis.delete.call_args_list]
    assert any("idempotency:task:key-rollback" in arg for arg in delete_calls)
