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
Idempotency keys are tracked in Redis under `idempotency:task:{key}`:
1. **Acquire**: Atomically executes `SET idempotency:task:{key} payload NX EX lock_ttl`.
   - If key does not exist: lock is acquired; execution proceeds.
   - If key exists with status `COMPLETED`: returns cached result immediately without re-execution.
   - If key exists with status `PROCESSING`: detects concurrent or redelivered run; suppresses duplicate execution.
2. **Complete**: Updates status to `COMPLETED`, records result payload, and sets retention TTL (24 hours).
3. **Transient Failure**: Calls `release(key)` to remove the lock, allowing the scheduled retry to re-acquire the lock.
4. **Permanent Failure**: Calls `fail(key)` with status `FAILED` and error details.

---

## 5. FastAPI Client Integration

### 5.1 Reusable `TaskService` (`backend/app/services/task_service.py`)
Provides safe async dispatching to avoid blocking FastAPI's uvloop:
- `submit_task(...)`: Runs `apply_async` off-thread (`asyncio.to_thread`), checks idempotency keys, and returns `TaskSubmissionResult`.
- `get_task_status(...)`: Queries `AsyncResult` state without blocking.
- `revoke_task(...)`: Dispatches control revocation for long-running or cancelled jobs.

### 5.2 API Endpoints (`/api/v1/tasks`)

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `POST` | `/api/v1/tasks/system/ping` | Enqueue diagnostic system ping task onto default queue | `202 Accepted` |
| `GET` | `/api/v1/tasks/{task_id}/status` | Query state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`) | `200 OK` |
| `GET` | `/api/v1/tasks/{task_id}/result` | Fetch task output or error details | `200 OK` |

Supports optional `Idempotency-Key` header on submission to prevent accidental duplicate clicks or retried HTTP submissions.

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
