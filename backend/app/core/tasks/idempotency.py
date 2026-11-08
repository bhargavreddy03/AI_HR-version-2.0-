"""Distributed task idempotency protection for at-least-once delivery guarantees."""

from __future__ import annotations

import functools
import json
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailableException
from app.core.redis import get_sync_redis_client
from app.core.tasks.base import TransientTaskError

logger = logging.getLogger("app.tasks.idempotency")

F = TypeVar("F", bound=Callable[..., Any])

IDEMPOTENCY_PREFIX = "idempotency:task:"


def format_scoped_key(
    key: str,
    tenant_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    task_type: str | None = None,
) -> str:
    """Format an idempotency key strictly scoped by tenant, user, and task type.

    Guarantees cross-tenant and cross-task isolation in distributed storage.
    """
    if key.startswith(IDEMPOTENCY_PREFIX):
        return key
    t_part = str(tenant_id) if tenant_id else "global"
    u_part = str(user_id) if user_id else "anonymous"
    type_part = str(task_type) if task_type else "general"
    return f"{IDEMPOTENCY_PREFIX}{t_part}:{u_part}:{type_part}:{key}"


# ------------------------------------------------------------------------------
# Lua Scripts for Atomic Idempotency State Transitions and Strict Lock Ownership
# ------------------------------------------------------------------------------

# Atomic submission registration from API layer (sets status=PENDING with task_id and tenant/user scope)
LUA_REGISTER_SUBMISSION = """
local key = KEYS[1]
local task_id = ARGV[1]
local lock_ttl = tonumber(ARGV[2])
local created_at = ARGV[3]
local tenant_id = ARGV[4]
local user_id = ARGV[5]
local task_type = ARGV[6]

local val = redis.call('GET', key)
if not val then
    local payload = cjson.encode({
        status = "PENDING",
        task_id = task_id,
        lock_token = cjson.null,
        tenant_id = (tenant_id and tenant_id ~= "") and tenant_id or cjson.null,
        user_id = (user_id and user_id ~= "") and user_id or cjson.null,
        task_type = (task_type and task_type ~= "") and task_type or cjson.null,
        created_at = created_at,
        result = cjson.null
    })
    redis.call('SET', key, payload, 'EX', lock_ttl)
    return {1, payload}
end

return {0, val}
"""

# Atomic worker acquisition: transitions from empty OR from PENDING (with matching task_id) to PROCESSING
LUA_ACQUIRE = """
local key = KEYS[1]
local task_id = ARGV[1]
local lock_token = ARGV[2]
local lock_ttl = tonumber(ARGV[3])
local now_str = ARGV[4]
local tenant_id = ARGV[5]
local user_id = ARGV[6]
local task_type = ARGV[7]

local val = redis.call('GET', key)
if not val then
    local payload = cjson.encode({
        status = "PROCESSING",
        task_id = task_id,
        lock_token = lock_token,
        tenant_id = (tenant_id and tenant_id ~= "") and tenant_id or cjson.null,
        user_id = (user_id and user_id ~= "") and user_id or cjson.null,
        task_type = (task_type and task_type ~= "") and task_type or cjson.null,
        created_at = now_str,
        started_at = now_str,
        result = cjson.null
    })
    redis.call('SET', key, payload, 'EX', lock_ttl)
    return {1, lock_token, payload}
end

local data = cjson.decode(val)
if data.status == "PENDING" and (data.task_id == task_id or task_id == "standalone") then
    data.status = "PROCESSING"
    data.lock_token = lock_token
    data.started_at = now_str
    if tenant_id and tenant_id ~= "" and (not data.tenant_id or data.tenant_id == cjson.null) then
        data.tenant_id = tenant_id
    end
    if user_id and user_id ~= "" and (not data.user_id or data.user_id == cjson.null) then
        data.user_id = user_id
    end
    if task_type and task_type ~= "" and (not data.task_type or data.task_type == cjson.null) then
        data.task_type = task_type
    end
    local new_payload = cjson.encode(data)
    redis.call('SET', key, new_payload, 'EX', lock_ttl)
    return {1, lock_token, new_payload}
end

return {0, cjson.null, val}
"""

# Atomic lock renewal: extends TTL strictly if lock_token matches current owner
LUA_RENEW_LOCK = """
local key = KEYS[1]
local lock_token = ARGV[1]
local extend_ttl = tonumber(ARGV[2])

if not lock_token or lock_token == "" then
    return 0
end

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
if not data.lock_token or data.lock_token == cjson.null or data.lock_token == "" then
    return 0
end

if data.lock_token ~= lock_token then
    return 0
end

redis.call('EXPIRE', key, extend_ttl)
return 1
"""

# Atomic state transition to DISPATCH_UNKNOWN when broker dispatch encounters an uncertain error
LUA_RECORD_DISPATCH_UNKNOWN = """
local key = KEYS[1]
local error_msg = ARGV[1]
local ttl = tonumber(ARGV[2])
local now_str = ARGV[3]

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
data.status = "DISPATCH_UNKNOWN"
data.dispatch_error = error_msg
data.updated_at = now_str
local new_payload = cjson.encode(data)
redis.call('SET', key, new_payload, 'EX', ttl)
return 1
"""

# Atomic state reconciliation: updates DISPATCH_UNKNOWN back to PENDING or active state
LUA_RECONCILE_DISPATCH = """
local key = KEYS[1]
local new_status = ARGV[1]
local ttl = tonumber(ARGV[2])
local now_str = ARGV[3]

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
data.status = new_status
data.reconciled_at = now_str
local new_payload = cjson.encode(data)
redis.call('SET', key, new_payload, 'EX', ttl)
return 1
"""

# Atomic task completion: stores result and COMPLETED status strictly if caller owns lock_token
LUA_COMPLETE = """
local key = KEYS[1]
local lock_token = ARGV[1]
local result_json = ARGV[2]
local task_id = ARGV[3]
local result_ttl = tonumber(ARGV[4])
local completed_at = ARGV[5]

-- Strictly reject missing or empty caller lock token
if not lock_token or lock_token == "" then
    return 0
end

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
-- Strictly reject if stored record has null, empty, or non-matching lock token
if not data.lock_token or data.lock_token == cjson.null or data.lock_token == "" then
    return 0
end

if data.lock_token ~= lock_token then
    return 0
end

data.status = "COMPLETED"
data.task_id = task_id
data.completed_at = completed_at
data.lock_token = cjson.null
if result_json and result_json ~= "" then
    data.result = cjson.decode(result_json)
else
    data.result = cjson.null
end

local new_payload = cjson.encode(data)
redis.call('SET', key, new_payload, 'EX', result_ttl)
return 1
"""

# Atomic lock release: deletes key strictly if lock_token matches current owner
LUA_RELEASE = """
local key = KEYS[1]
local lock_token = ARGV[1]

if not lock_token or lock_token == "" then
    return 0
end

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
if not data.lock_token or data.lock_token == cjson.null or data.lock_token == "" then
    return 0
end

if data.lock_token == lock_token then
    redis.call('DEL', key)
    return 1
end

return 0
"""

# Atomic permanent failure: marks FAILED strictly if caller holds the matching lock_token
LUA_FAIL = """
local key = KEYS[1]
local lock_token = ARGV[1]
local error_msg = ARGV[2]
local task_id = ARGV[3]
local ttl = tonumber(ARGV[4])
local failed_at = ARGV[5]

if not lock_token or lock_token == "" then
    return 0
end

local val = redis.call('GET', key)
if not val then
    return 0
end

local data = cjson.decode(val)
if not data.lock_token or data.lock_token == cjson.null or data.lock_token == "" then
    return 0
end

if data.lock_token ~= lock_token then
    return 0
end

data.status = "FAILED"
data.task_id = task_id
data.failed_at = failed_at
data.error = error_msg
data.lock_token = cjson.null

local new_payload = cjson.encode(data)
redis.call('SET', key, new_payload, 'EX', ttl)
return 1
"""


class IdempotencyManager:
    """Manages distributed idempotency locks and cached execution results via Redis."""

    def __init__(
        self,
        sync_client: redis.Redis[Any] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._sync_client = sync_client

    @property
    def sync_client(self) -> redis.Redis[Any]:
        if self._sync_client is None:
            self._sync_client = get_sync_redis_client(self.settings)
        return self._sync_client

    def _format_key(self, key: str) -> str:
        if key.startswith(IDEMPOTENCY_PREFIX):
            return key
        return f"{IDEMPOTENCY_PREFIX}{key}"

    def register_submission(
        self,
        key: str,
        task_id: str,
        lock_ttl: int = 360,
        tenant_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        task_type: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Atomically register task submission with initial PENDING state and real task ID.

        Returns:
            (True, None) if registered fresh.
            (False, existing_payload) if key already exists (duplicate submission).
        Raises:
            ServiceUnavailableException if Redis is unreachable or operation fails.
        """
        redis_key = self._format_key(key)
        created_at = datetime.now(UTC).isoformat()
        t_str = str(tenant_id) if tenant_id else ""
        u_str = str(user_id) if user_id else ""
        type_str = str(task_type) if task_type else ""
        try:
            res = self.sync_client.eval(
                LUA_REGISTER_SUBMISSION,
                1,
                redis_key,
                task_id,
                str(lock_ttl),
                created_at,
                t_str,
                u_str,
                type_str,
            )
            success = bool(res[0])
            payload_str = res[1]
            if success:
                return True, None
            data = json.loads(str(payload_str)) if payload_str else None
            return False, data
        except Exception as exc:
            logger.error("Redis failure during idempotency registration: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable. Unable to guarantee task idempotency.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    def acquire(
        self,
        key: str,
        task_id: str,
        lock_ttl: int = 360,
        tenant_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        task_type: str | None = None,
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """Attempt to acquire idempotency lock for task execution.

        Returns:
            (True, lock_token, None) if lock was successfully acquired.
            (False, None, payload) if key already exists in a non-acquirable state.
        Raises:
            ServiceUnavailableException if Redis operation fails.
        """
        redis_key = self._format_key(key)
        lock_token = uuid.uuid4().hex
        now_str = datetime.now(UTC).isoformat()
        t_str = str(tenant_id) if tenant_id else ""
        u_str = str(user_id) if user_id else ""
        type_str = str(task_type) if task_type else ""

        try:
            res = self.sync_client.eval(
                LUA_ACQUIRE,
                1,
                redis_key,
                task_id,
                lock_token,
                str(lock_ttl),
                now_str,
                t_str,
                u_str,
                type_str,
            )
            success = bool(res[0])
            if success:
                returned_token = str(res[1]) if res[1] else lock_token
                return True, returned_token, None

            existing_str = res[2]
            if existing_str:
                try:
                    data = json.loads(str(existing_str))
                    return False, None, data
                except (json.JSONDecodeError, TypeError):
                    pass
            return False, None, {"status": "PROCESSING", "task_id": "unknown"}
        except Exception as exc:
            logger.error("Redis failure during idempotency acquire: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    def renew(
        self,
        key: str,
        lock_token: str | None,
        extend_ttl: int = 360,
    ) -> bool:
        """Atomically extend lock lifetime for the active owner holding lock_token."""
        if not lock_token or not lock_token.strip():
            logger.warning("Rejected renew() attempt without valid lock_token for key %s", key)
            return False

        redis_key = self._format_key(key)
        try:
            res = self.sync_client.eval(
                LUA_RENEW_LOCK,
                1,
                redis_key,
                lock_token,
                str(extend_ttl),
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure during lock renewal for key %s: %s", key, exc)
            return False

    def complete(
        self,
        key: str,
        result: Any,
        task_id: str,
        lock_token: str | None = None,
        result_ttl: int = 86400,
    ) -> bool:
        """Store completed execution result under the idempotency key with retention TTL.

        Strictly enforces that only the caller holding the matching lock_token can complete.
        Rejects missing tokens, null stored tokens, and stale tokens.
        """
        if not lock_token or not lock_token.strip():
            logger.warning("Rejected complete() attempt without valid lock_token for key %s", key)
            return False

        redis_key = self._format_key(key)
        now_str = datetime.now(UTC).isoformat()
        try:
            result_json = json.dumps(result)
        except (TypeError, ValueError):
            result_json = json.dumps(str(result))

        try:
            res = self.sync_client.eval(
                LUA_COMPLETE,
                1,
                redis_key,
                lock_token,
                result_json,
                task_id,
                str(result_ttl),
                now_str,
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure during idempotency complete: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable during completion.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    def fail(
        self,
        key: str,
        error: str,
        task_id: str,
        lock_token: str | None = None,
        ttl: int = 3600,
    ) -> bool:
        """Mark task as permanently failed under the idempotency key strictly if lock_token matches."""
        if not lock_token or not lock_token.strip():
            logger.warning("Rejected fail() attempt without valid lock_token for key %s", key)
            return False

        redis_key = self._format_key(key)
        now_str = datetime.now(UTC).isoformat()

        try:
            res = self.sync_client.eval(
                LUA_FAIL,
                1,
                redis_key,
                lock_token,
                error,
                task_id,
                str(ttl),
                now_str,
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure during idempotency fail: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable during failure record.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    def release(self, key: str, lock_token: str | None = None) -> bool:
        """Release lock allowing subsequent retry. Strictly enforces matching lock_token."""
        if not lock_token or not lock_token.strip():
            logger.warning("Rejected release() attempt without valid lock_token for key %s", key)
            return False

        redis_key = self._format_key(key)
        try:
            res = self.sync_client.eval(
                LUA_RELEASE,
                1,
                redis_key,
                lock_token,
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure during idempotency release: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable during release.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    def force_delete(self, key: str) -> bool:
        """Administrative / test reset utility to delete an idempotency key unconditionally."""
        redis_key = self._format_key(key)
        try:
            return bool(self.sync_client.delete(redis_key))
        except Exception as exc:
            logger.error("Redis failure during force_delete: %s", exc)
            return False

    @classmethod
    async def register_submission_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        task_id: str,
        lock_ttl: int = 360,
        tenant_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        task_type: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Asynchronously register a task submission with status PENDING and real task ID.

        Raises:
            ServiceUnavailableException if Redis operation fails.
        """
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        created_at = datetime.now(UTC).isoformat()
        t_str = str(tenant_id) if tenant_id else ""
        u_str = str(user_id) if user_id else ""
        type_str = str(task_type) if task_type else ""
        try:
            res = await client.eval(
                LUA_REGISTER_SUBMISSION,
                1,
                redis_key,
                task_id,
                str(lock_ttl),
                created_at,
                t_str,
                u_str,
                type_str,
            )
            success = bool(res[0])
            payload_str = res[1]
            if success:
                return True, None
            data = json.loads(str(payload_str)) if payload_str else None
            return False, data
        except Exception as exc:
            logger.error("Redis failure in register_submission_async Lua: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable. Unable to guarantee task idempotency.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    @classmethod
    async def acquire_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        task_id: str,
        lock_ttl: int = 360,
        tenant_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        task_type: str | None = None,
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """Asynchronously attempt to acquire idempotency lock for FastAPI endpoints or tasks."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        lock_token = uuid.uuid4().hex
        now_str = datetime.now(UTC).isoformat()
        t_str = str(tenant_id) if tenant_id else ""
        u_str = str(user_id) if user_id else ""
        type_str = str(task_type) if task_type else ""
        try:
            res = await client.eval(
                LUA_ACQUIRE,
                1,
                redis_key,
                task_id,
                lock_token,
                str(lock_ttl),
                now_str,
                t_str,
                u_str,
                type_str,
            )
            success = bool(res[0])
            if success:
                returned_token = str(res[1]) if res[1] else lock_token
                return True, returned_token, None
            existing_str = res[2]
            if existing_str:
                try:
                    data = json.loads(str(existing_str))
                    return False, None, data
                except (json.JSONDecodeError, TypeError):
                    pass
            return False, None, {"status": "PROCESSING", "task_id": "unknown"}
        except Exception as exc:
            logger.error("Redis failure in acquire_async Lua: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc

    @classmethod
    async def renew_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        lock_token: str | None,
        extend_ttl: int = 360,
    ) -> bool:
        """Asynchronously extend lock lifetime for the active owner holding lock_token."""
        if not lock_token or not lock_token.strip():
            return False
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        try:
            res = await client.eval(
                LUA_RENEW_LOCK,
                1,
                redis_key,
                lock_token,
                str(extend_ttl),
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure during async lock renewal: %s", exc)
            return False

    @classmethod
    async def record_dispatch_unknown_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        error_msg: str,
        ttl: int = 600,
    ) -> bool:
        """Record recoverable uncertain dispatch state when Celery dispatch encounters an exception."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        now_str = datetime.now(UTC).isoformat()
        try:
            res = await client.eval(
                LUA_RECORD_DISPATCH_UNKNOWN,
                1,
                redis_key,
                error_msg,
                str(ttl),
                now_str,
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure recording DISPATCH_UNKNOWN: %s", exc)
            return False

    @classmethod
    async def reconcile_dispatch_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        new_status: str = "PENDING",
        ttl: int = 360,
    ) -> bool:
        """Atomically reconcile DISPATCH_UNKNOWN state back to PENDING or active state."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        now_str = datetime.now(UTC).isoformat()
        try:
            res = await client.eval(
                LUA_RECONCILE_DISPATCH,
                1,
                redis_key,
                new_status,
                str(ttl),
                now_str,
            )
            return bool(res)
        except Exception as exc:
            logger.error("Redis failure reconciling dispatch: %s", exc)
            return False

    @classmethod
    async def get_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
    ) -> dict[str, Any] | None:
        """Asynchronously retrieve idempotency payload from Redis."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}" if not key.startswith(IDEMPOTENCY_PREFIX) else key
        try:
            raw = await client.get(redis_key)
            if raw:
                try:
                    return json.loads(str(raw))  # type: ignore[no-any-return]
                except (json.JSONDecodeError, TypeError):
                    return None
            return None
        except Exception as exc:
            logger.error("Redis failure in get_async: %s", exc)
            raise ServiceUnavailableException(
                "Idempotency service unavailable.",
                error_code="IDEMPOTENCY_UNAVAILABLE",
            ) from exc


class LockHeartbeat:
    """Background heartbeat thread to periodically renew lock TTL while task is running."""

    def __init__(
        self,
        manager: IdempotencyManager,
        key: str,
        lock_token: str,
        interval: float,
        extend_ttl: int,
    ) -> None:
        self.manager = manager
        self.key = key
        self.lock_token = lock_token
        self.interval = interval
        self.extend_ttl = extend_ttl
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        def _run() -> None:
            while not self._stop_event.wait(self.interval):
                try:
                    renewed = self.manager.renew(self.key, self.lock_token, self.extend_ttl)
                    if not renewed:
                        logger.warning("Lock renewal failed or lost ownership for key %s", self.key)
                        break
                except Exception as exc:
                    logger.warning("Exception during lock heartbeat renewal: %s", exc)
                    break

        self._thread = threading.Thread(target=_run, daemon=True, name="lock-heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)


def idempotent_task(
    key_param: str = "idempotency_key",
    lock_ttl: int = 360,
    result_ttl: int = 86400,
) -> Callable[[F], F]:
    """Decorator ensuring Celery task execution is idempotent under at-least-once delivery.

    - Scopes idempotency keys across tenants, users, and task types.
    - Uses properly bounded leases exceeding maximum execution time (CELERY_TASK_TIME_LIMIT).
    - Periodically renews worker lock while task executes.
    - Strictly checks ownership tokens during renewal, completion, failure, and release.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            idempotency_key = kwargs.get(key_param)
            if not idempotency_key:
                return fn(*args, **kwargs)

            task_inst = args[0] if (args and hasattr(args[0], "request")) else None
            req = getattr(task_inst, "request", None) if task_inst else None
            task_id = getattr(req, "id", None) or "standalone"
            req_headers = getattr(req, "headers", None) or {}

            # Determine scoped key from Celery headers or runtime arguments
            if isinstance(req_headers, dict) and req_headers.get("idempotency_scoped_key"):
                scoped_key = str(req_headers["idempotency_scoped_key"])
            else:
                t_id = kwargs.get("tenant_id") or (
                    req_headers.get("tenant_id") if isinstance(req_headers, dict) else None
                )
                u_id = kwargs.get("user_id") or (
                    req_headers.get("user_id") if isinstance(req_headers, dict) else None
                )
                t_type = getattr(task_inst, "name", None) or getattr(fn, "__name__", None)
                scoped_key = format_scoped_key(
                    key=str(idempotency_key),
                    tenant_id=t_id,
                    user_id=u_id,
                    task_type=t_type,
                )

            manager = IdempotencyManager()
            settings = manager.settings

            # Ensure lease is safely bounded to exceed hard task time limit
            bounded_lock_ttl = max(lock_ttl, settings.CELERY_TASK_TIME_LIMIT + 60)
            heartbeat_interval = min(bounded_lock_ttl / 4.0, 30.0)

            acquired, lock_token, existing = manager.acquire(
                key=scoped_key,
                task_id=task_id,
                lock_ttl=bounded_lock_ttl,
            )

            if not acquired and existing:
                if existing.get("status") == "COMPLETED":
                    logger.info(
                        "Idempotent task returning cached result: key=%s, task_id=%s",
                        scoped_key,
                        task_id,
                    )
                    return existing.get("result")
                if existing.get("status") in ("PROCESSING", "PENDING"):
                    logger.warning(
                        "Duplicate task execution suppressed (already running): key=%s, owner_task_id=%s",
                        scoped_key,
                        existing.get("task_id"),
                    )
                    return {
                        "status": "duplicate_execution_suppressed",
                        "idempotency_key": idempotency_key,
                        "original_task_id": existing.get("task_id"),
                    }

            # Start active lock heartbeat while task executes
            heartbeat = None
            if lock_token:
                heartbeat = LockHeartbeat(
                    manager=manager,
                    key=scoped_key,
                    lock_token=lock_token,
                    interval=heartbeat_interval,
                    extend_ttl=bounded_lock_ttl,
                )
                heartbeat.start()

            try:
                result = fn(*args, **kwargs)
                manager.complete(
                    key=scoped_key,
                    result=result,
                    task_id=task_id,
                    lock_token=lock_token,
                    result_ttl=result_ttl,
                )
                return result
            except TransientTaskError:
                # Release lock with ownership token so retry can acquire
                manager.release(scoped_key, lock_token=lock_token)
                raise
            except Exception as exc:
                manager.fail(
                    key=scoped_key,
                    error=str(exc),
                    task_id=task_id,
                    lock_token=lock_token,
                )
                raise
            finally:
                if heartbeat is not None:
                    heartbeat.stop()

        return wrapper  # type: ignore[return-value]

    return decorator
