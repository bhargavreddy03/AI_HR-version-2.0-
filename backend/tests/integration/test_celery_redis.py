"""Integration tests verifying Celery execution with live Redis broker, result backend, and real worker process."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

import pytest
import redis
from celery.result import AsyncResult

from app.core.celery_app import celery_app
from app.core.config import Settings
from app.core.redis import get_sync_redis_client
from app.core.tasks.idempotency import IdempotencyManager
from app.core.tasks.system import system_ping
from app.modules.documents.tasks import parse_document

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
    while time.time() - start_time < 10.0:
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
        time.sleep(0.3)

    if not ready:
        proc.kill()
        proc.wait()
        raise TimeoutError("Celery worker did not respond to ping within 10 seconds")

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
    # 1. Dispatch task to live Redis broker
    res = system_ping.apply_async(args=("live-redis-test",), queue="default")
    assert res.id is not None

    # 2. Await actual asynchronous execution by the live worker process
    result = res.get(timeout=10.0)
    assert res.successful() is True
    assert result["status"] == "pong"
    assert result["message"] == "live-redis-test"

    # 3. Verify result directly in configured live result backend via AsyncResult
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

    # Enqueue a task to document_processing without eager execution
    async_doc = parse_document.apply_async(
        kwargs={
            "document_id": "live-doc-123",
            "tenant_id": "tenant-live-456",
        },
        queue="document_processing",
    )
    assert async_doc.id is not None

    # Check that document_processing list grew in Redis broker
    new_doc_len = r_broker.llen("document_processing")
    assert new_doc_len >= initial_doc_len + 1

    # Cleanup the test message from the queue list
    raw_msg = r_broker.rpop("document_processing")
    assert raw_msg is not None


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_idempotency_lifecycle() -> None:
    """Verify IdempotencyManager atomic registration, lock tokens, and safe concurrent protection."""
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    test_key = "live-test-key-safe-locks"
    manager.release(test_key)

    # 1. API registers submission with assigned task ID
    registered, existing = manager.register_submission(test_key, task_id="task-live-1", lock_ttl=60)
    assert registered is True
    assert existing is None

    # 2. Duplicate API submission rejected with duplicate flag
    registered2, existing2 = manager.register_submission(
        test_key, task_id="task-live-2", lock_ttl=60
    )
    assert registered2 is False
    assert existing2 is not None
    assert existing2["task_id"] == "task-live-1"
    assert existing2["status"] == "PENDING"

    # 3. Legitimate worker for task-live-1 acquires lock: transitions PENDING -> PROCESSING with lock_token
    acquired, lock_token, err_payload = manager.acquire(
        test_key, task_id="task-live-1", lock_ttl=60
    )
    assert acquired is True
    assert lock_token is not None
    assert err_payload is None

    # 4. Another concurrent worker attempts to acquire: rejected (already PROCESSING)
    acquired_dup, token_dup, dup_payload = manager.acquire(
        test_key, task_id="task-live-dup", lock_ttl=60
    )
    assert acquired_dup is False
    assert token_dup is None
    assert dup_payload is not None
    assert dup_payload["status"] == "PROCESSING"

    # 5. Worker with WRONG lock_token attempts to complete: rejected (cannot overwrite)
    completed_wrong = manager.complete(
        test_key,
        result={"done": True},
        task_id="task-live-dup",
        lock_token="stale-invalid-token",
    )
    assert completed_wrong is False

    # 6. Worker with WRONG lock_token attempts to release: rejected (cannot delete other worker's lock)
    released_wrong = manager.release(test_key, lock_token="stale-invalid-token")
    assert released_wrong is False

    # 7. Worker with VALID lock_token completes: succeeds and records COMPLETED
    completed_valid = manager.complete(
        test_key,
        result={"status": "pong"},
        task_id="task-live-1",
        lock_token=lock_token,
        result_ttl=60,
    )
    assert completed_valid is True

    # 8. Subsequent acquire sees COMPLETED and returns cached data
    acquired_after, token_after, final_payload = manager.acquire(
        test_key, task_id="task-live-3", lock_ttl=60
    )
    assert acquired_after is False
    assert final_payload is not None
    assert final_payload["status"] == "COMPLETED"
    assert final_payload["result"] == {"status": "pong"}

    # Cleanup
    manager.release(test_key)
