# Step 3.5 — Redis and Celery Background Processing Foundation

## 1. Executive Summary & Objective

Step 3.5 establishes the enterprise asynchronous task processing and worker execution foundation for the AI-Powered Recruitment & HR Intelligence Platform. Built strictly upon the approved Step 2 architecture specifications (`03_system_architecture.md`, `07_authentication_authorization.md`, `13_resume_processing_pipeline.md`, and `MICROSERVICE_EXTRACTION_GUIDE.md`), this milestone integrates:

1. **Centralized Celery 5.4+ Application Layer**: Robust, non-blocking asynchronous architecture under `backend/app/core/celery_app.py` leveraging existing Redis 7 infrastructure as both message broker and result backend.
2. **Dedicated Queue Architecture & Workload Routing**: Explicit separation of responsibilities across 7 specialized direct queues (`default`, `document_processing`, `resume_parsing`, `embedding_generation`, `candidate_matching`, `notifications`, `reporting`) with zero cross-queue starvation.
3. **Enterprise Task Reliability & Failure Policies**: Automated exponential backoff with jitter for transient errors (`TransientTaskError`), strict immediate non-retry for validation and business errors (`PermanentTaskError`), and execution timeouts (`task_time_limit = 300s`, `task_soft_time_limit = 240s`).
4. **Distributed Idempotency Protection**: Redis-backed atomic distributed locks (`IdempotencyManager` and `@idempotent_task`) ensuring safe execution under Celery's at-least-once delivery guarantees and preventing duplicate task submission.
5. **FastAPI Client Integration**: Reusable async `TaskService` and secure REST endpoints (`/api/v1/tasks/system/ping`, `/api/v1/tasks/{task_id}/status`, `/api/v1/tasks/{task_id}/result`) enabling asynchronous dispatching without event-loop blocking.
6. **Docker Orchestration & Container Health**: Production and development Compose configurations introducing `celery_worker` with graceful shutdown (`SIGTERM`, 30s grace period) and internal networking isolation.

---

## 2. Asynchronous Architecture & Queue Topology

### 2.1 Queue Responsibilities

Workloads are segregated into 7 dedicated direct queues to eliminate head-of-line blocking and guarantee high responsiveness for interactive tasks:

| Queue Name | Routing Key | Workload Responsibilities | Concurrency / Worker Focus |
|---|---|---|---|
| `default` | `default` | System telemetry, diagnostic health pings, lightweight housekeeping | 2 processes / baseline |
| `document_processing` | `document_processing` | Binary document ingestion, OCR fallback parsing (Tesseract/Textract) | IO-intensive / external API |
| `resume_parsing` | `resume_parsing` | PDF text extraction (`pdfplumber`), section parsing, entity recognition | CPU-intensive parsing |
| `embedding_generation` | `embedding_generation` | Vector generation, pgvector indexing, model dimension mapping | High-throughput batch / GPU |
| `candidate_matching` | `candidate_matching` | Vector similarity cosine search, ranking algorithms, filtering | Memory & CPU-bound |
| `notifications` | `notifications` | Candidate/recruiter emails, transactional SMS, outbound webhooks | Network IO / rate-limited |
| `reporting` | `reporting` | Large-scale Excel/PDF exports, compliance audit reporting | Background batch / memory-safe |

### 2.2 Task Lifecycle & Delivery Semantics

```
[ FastAPI Producer ]
       │
       ▼ (apply_async / to_thread)
[ Redis Message Broker (DB 1) ]
       │
       ▼ (Fair Prefetch = 1, Acks Late = True)
[ Celery Worker Pool ] ───(Acquire Idempotency Lock)───► [ Redis DB 0 (Idempotency) ]
       │                                                         │
       ├──► Transient Failure ──► Retry (Exp. Backoff + Jitter) ──┤ (Release Lock)
       ├──► Permanent Error   ──► Abort & Log Structured Error ──┤ (Fail Lock)
       └──► Success Execution ──► Store Result ───────────────────┘ (Complete Lock)
                                       │
                                       ▼
                       [ Redis Result Backend (DB 2) ]
                                       │
                                       ▼ (AsyncResult Poll)
                             [ FastAPI Client API ]
```

#### At-Least-Once Delivery Guarantees
Celery is configured with `task_acks_late = True` and `task_reject_on_worker_lost = True`. If a worker terminates abruptly or crashes mid-task, unacknowledged messages are safely returned to the broker and redelivered to an active worker. 

Because messages can be redelivered, tasks are designed to be strictly idempotent using the distributed lock and cache protocol described in Section 4.

---

## 3. Celery Configuration Reference

### 3.1 Serialization & Worker Mechanics
- **Serialization**: Strictly `json` for both tasks and results (`task_serializer="json"`, `result_serializer="json"`, `accept_content=["json"]`). Pickle and insecure binary formats are strictly forbidden.
- **Timezone**: UTC-aware (`timezone="UTC"`, `enable_utc=True`).
- **Prefetch Multiplier**: `worker_prefetch_multiplier = 1` enforces fair task distribution, preventing idle workers while long-running parsing tasks run.
- **Worker Concurrency**: Configurable via `CELERY_WORKER_CONCURRENCY` (default: `2`).
- **Time Limits**: Hard timeout `CELERY_TASK_TIME_LIMIT = 300s`, soft timeout `CELERY_TASK_SOFT_TIME_LIMIT = 240s`.
- **Result Expiration**: Task results expire in Redis after `CELERY_RESULT_EXPIRES = 86400s` (24 hours).
- **Startup Resilience**: `broker_connection_retry_on_startup = True` prevents startup race crashes.

### 3.2 Redis Database Index Segregation
The platform uses dedicated Redis database indexes to avoid key collisions and isolate evictions:
- **Index 0 (`REDIS_DB=0`)**: Application caching, session token version fences, distributed idempotency locks.
- **Index 1 (`CELERY_BROKER_URL`)**: Celery message broker task queues and kombu exchange channels.
- **Index 2 (`CELERY_RESULT_BACKEND`)**: Celery AsyncResult storage and task state tracking.

---

## 4. Reliability, Error Handling & Idempotency Strategy

### 4.1 Error Hierarchy
All background processing errors inherit from `CeleryTaskError` (`app.core.tasks.base`):

```python
class CeleryTaskError(Exception):
    """Base exception for all background Celery task failures."""

class TransientTaskError(CeleryTaskError):
    """Transient task error that triggers exponential backoff with jitter."""

class PermanentTaskError(CeleryTaskError):
    """Permanent task error that must not be retried (validation/business rule)."""
```

### 4.2 Retry Policy
Tasks supporting automated retries define:
- `autoretry_for = (TransientTaskError,)`
- `retry_backoff = True` (exponential backoff factor: $2^{\text{attempt}}$ seconds)
- `retry_backoff_max = 300` (capped maximum backoff ceiling)
- `retry_jitter = True` (randomized jitter prevents thundering herd against external dependencies)
- `max_retries = 3` (finite retry limit)

Permanent errors (`PermanentTaskError`, Pydantic validation errors) bypass the retry loop and fail immediately with structured error logs.

### 4.3 Structured Logging & Security Sanitization
The abstract `BaseTask` hooks into Celery's lifecycle (`before_start`, `on_success`, `on_retry`, `on_failure`) and provides automatic recursive sanitization:
- Sensitive parameters (`password`, `secret`, `token`, `key`, `authorization`, `mfa_secret`, `pepper`, `jwt`, `credential`) are masked with `******` before telemetry logging.
- Structured execution timing measures runtime down to hundredths of a millisecond (`duration_ms`).

### 4.4 Distributed Idempotency Protocol (`IdempotencyManager`)
Idempotency keys are tracked in Redis under strictly scoped keys `idempotency:task:{tenant_id}:{user_id}:{task_type}:{key}` using atomic Lua scripts and unique lock ownership tokens:
1. **Multi-Tenant Key Scoping (`format_scoped_key`)**:
   - Every idempotency key is partitioned by `tenant_id`, `user_id`, and `task_type` (`idempotency:task:{tenant_id}:{user_id}:{task_type}:{key}`).
   - Client-provided keys are never trusted or returned un-namespaced, even if they begin with `idempotency:task:`.
   - Guarantees complete cross-tenant and cross-task isolation. Malicious prefix injections cannot escape the caller's tenant boundary. Two distinct organizations or users submitting with identical client keys will never collide or receive each other's task ID.
2. **API Submission Registration (`LUA_REGISTER_SUBMISSION`)**:
   - Atomically records initial submission under the scoped key with status `PENDING`, the real Celery `task_id`, tenant/user metadata, and state-dependent `DEFAULT_SUBMISSION_TTL` (24 hours).
   - Tasks may wait in Celery queues for extended periods without expiring prematurely or permitting duplicate client dispatch.
   - Strictly separates queue submission retention (24 hours) from active worker lock leases.
   - If key already exists: enforces tenant ownership verification before returning existing payload, and suppresses duplicate dispatch.
3. **Worker Acquisition (`LUA_ACQUIRE`)**:
   - Generates a unique `lock_token` (UUID).
   - When worker begins execution, transitions state from `PENDING` (or recoverable `DISPATCH_UNKNOWN` matching `task_id`) to `PROCESSING`, assigns the `lock_token`, and sets the active worker execution lease (`bounded_lock_ttl >= 360s`).
   - If key is already `PROCESSING` by another worker or `COMPLETED`: rejects acquisition, returning the existing record and suppressing duplicate execution.
4. **Fail-Closed Execution Model (`@idempotent_task`)**:
   - Underlying task execution (`fn`) is **strictly permitted if and only if** Redis confirms successful lock acquisition and returns a valid `lock_token`.
   - If lock acquisition fails:
     - `COMPLETED`: Returns cached result immediately.
     - `PROCESSING` or `PENDING`: Suppresses duplicate execution safely.
     - `FAILED`: Rejects automatic execution without running.
     - `DISPATCH_UNKNOWN`: Permits execution only if the worker's `task_id` matches the original registered `task_id`.
     - Unknown states, missing records, or Redis connectivity errors: **Fail closed immediately**, raising `PermanentTaskError` and preventing unprotected execution.
5. **Bounded Leases & Resilient Lock Heartbeat (`LUA_RENEW_LOCK` & `LockHeartbeat`)**:
   - Active worker lock lease is automatically bounded to exceed the maximum Celery task execution time (`max(lock_ttl, settings.CELERY_TASK_TIME_LIMIT + 60)`).
   - While the task is actively executing, a background daemon `LockHeartbeat` periodically calls `renew_with_reason()` using `LUA_RENEW_LOCK`, extending the key's lease TTL.
   - **Transient Network Errors vs Confirmed Loss**:
     - `LockHeartbeat` distinguishes transient Redis connectivity failures (`ConnectionError`, `TimeoutError`) from confirmed lock ownership loss (`KEY_EXPIRED`, `TOKEN_MISMATCH`, `NO_ACTIVE_LOCK`).
     - Transient network drops are retried within a bounded window (up to `max_consecutive_network_failures=3`).
     - Explicit Redis rejections (`TOKEN_MISMATCH`, `KEY_EXPIRED`) immediately mark ownership lost.
     - If lock ownership was confirmed lost during execution or if `complete()` returns failure, the task aborts and raises `PermanentTaskError` rather than claiming false success.
6. **Safe Broker Dispatch Failure & Atomic Reconciliation (`DISPATCH_UNKNOWN`)**:
   - If Celery broker dispatch raises an exception (e.g., broker timeout or connection drop where broker may have already accepted the message), the idempotency record is **not** deleted.
   - The state is conditionally updated to `DISPATCH_UNKNOWN` via `LUA_RECORD_DISPATCH_UNKNOWN`:
     - Verifies `expected_task_id`.
     - **Never overwrites** active or terminal states (`PROCESSING`, `COMPLETED`, `FAILED`).
     - **Never overwrites** if an active worker `lock_token` has already been assigned.
     - Preserves completed task results even if the worker finished before the API publisher timed out.
   - When the client retries with the same `Idempotency-Key`, `TaskService` inspects the Celery result backend and broker:
     - If the task was already received and is executing/finished (`STARTED`, `SUCCESS`, `FAILURE`, `RETRY`), it reconciles to that status and returns `duplicate=True` without redispatching.
     - If the task was not yet picked up, it re-dispatches using the **exact same** `task_id` and reconciles status via `LUA_RECONCILE_DISPATCH` with `expected_task_id` verification.
7. **Completion Protection (`LUA_COMPLETE`)**:
   - Atomically sets status to `COMPLETED` and stores the serialized result with retention TTL (`result_ttl = 86400s`, 24 hours) **strictly if** the record's `lock_token` matches the current worker.
   - Stale or expired workers can never overwrite new lock holders.
8. **Transient Failure (`LUA_RELEASE`)**:
   - Releases the active worker lock lease and restores the record to `PENDING` with `DEFAULT_SUBMISSION_TTL` **strictly if** the `lock_token` matches the current worker, allowing the scheduled retry to safely re-acquire while blocking concurrent duplicate submissions during retry backoff.
9. **Permanent Failure (`LUA_FAIL`)**:
   - Marks the task as `FAILED` with retention TTL **strictly if** the `lock_token` matches the current worker.
10. **External Side Effects & Distributed Transactions**:
   - The distributed lock and idempotency state machine guarantees single-worker execution boundaries within the Celery and Redis infrastructure.
   - External side effects (such as third-party HTTP webhooks, external payment APIs, or transactional emails) must additionally supply business-level idempotency tokens or utilize transactional outbox mechanisms to guarantee end-to-end exactly-once business semantics across external boundaries.

---

## 5. FastAPI Client Integration & Multi-Tenant Authorization

### 5.1 Reusable `TaskService` (`backend/app/services/task_service.py`)
Provides safe async dispatching to avoid blocking FastAPI's uvloop:
- `submit_task(...)`: Assigns the real task ID upfront, executes off-thread (`asyncio.to_thread`), checks idempotency keys atomically, records task ownership metadata (`task:meta:{task_id}`) in Redis, and returns `TaskSubmissionResult`.
- `get_task_metadata(...)`: Retrieves ownership metadata (`tenant_id`, `user_id`, `queue`) for authorization verification.
- `get_task_status(...)`: Queries `AsyncResult` state without blocking.
- `revoke_task(...)`: Dispatches control revocation for long-running or cancelled jobs.

### 5.2 API Endpoints (`/api/v1/tasks`)

| Method | Endpoint | Description | Status Code | Auth Required |
|---|---|---|---|---|
| `POST` | `/api/v1/tasks/system/ping` | Enqueue diagnostic system ping task onto default queue | `202 Accepted` | Yes (`require_authenticated_user`) |
| `GET` | `/api/v1/tasks/{task_id}/status` | Query state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`) | `200 OK` | Yes (`require_authenticated_user`) |
| `GET` | `/api/v1/tasks/{task_id}/result` | Fetch task output or error details | `200 OK` | Yes (`require_authenticated_user`) |

#### Multi-Tenant Security & Isolation Boundary
1. **Authentication Required**: All task endpoints require a valid session via `require_authenticated_user`. Unauthenticated calls are rejected with 401 Unauthorized.
2. **Tenant Isolation**: When querying task status or results, the application checks `task:meta:{task_id}` against the user's active `tenant_id`:
   - If the task belongs to another organization, access is denied immediately with 403 Forbidden (`TENANT_MISMATCH`).
   - If the task has no tenant metadata and was not created by the user (and the user is not superadmin), access is denied with 403 Forbidden or 404 Not Found.
3. **Idempotency Header**: Supports optional `Idempotency-Key` header on submission to prevent duplicate task submissions across network retries.

---

## 6. Docker Infrastructure & Orchestration

### 6.1 Compose Service Configuration (`infrastructure/docker/docker-compose.yml`)
```yaml
  celery_worker:
    build:
      context: ../../backend
      dockerfile: Dockerfile
    container_name: ai_hr_celery_worker
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - ${ENV_FILE:-../../.env}
    command: >-
      celery -A app.core.celery_app:celery_app worker
      --loglevel=INFO
      -Q default,document_processing,resume_parsing,embedding_generation,candidate_matching,notifications,reporting
      --concurrency=${CELERY_WORKER_CONCURRENCY:-2}
    stop_signal: SIGTERM
    stop_grace_period: 30s
    healthcheck:
      test: ["CMD-SHELL", "python -m app.core.celery_health || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 3
```

- **Network Isolation**: Worker does not expose or bind host ports.
- **Graceful Shutdown**: `stop_signal: SIGTERM` and `stop_grace_period: 30s` allow in-flight tasks to finish before shutdown.
- **Health Check Probe**: `python -m app.core.celery_health` confirms broker connectivity and responsiveness.

---

## 7. Local Development & Operational Commands

### 7.1 Running Worker Locally
```bash
cd backend
# Run standalone worker entrypoint
.venv/Scripts/python.exe -m app.worker

# Or via Celery CLI
.venv/Scripts/celery -A app.core.celery_app:celery_app worker --loglevel=INFO -Q default,document_processing,resume_parsing,embedding_generation,candidate_matching,notifications,reporting -c 2
```

### 7.2 Running Docker Stack
```bash
# Start local development stack with worker
docker compose --env-file .env.dev -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.dev.yml up -d postgres redis celery_worker
```

### 7.3 Health Check Probe
```bash
cd backend
.venv/Scripts/python.exe -m app.core.celery_health
```

### 7.4 Running Test Suite
```bash
cd backend
# Run all unit tests
.venv/Scripts/pytest tests -v -m "not integration"

# Run Celery and Redis integration tests (with Redis running on 6379)
.venv/Scripts/pytest tests/integration/test_celery_redis.py -v
```
