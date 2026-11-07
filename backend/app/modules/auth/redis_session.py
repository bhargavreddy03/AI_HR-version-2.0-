"""Redis session registry, atomic monotonic version fences, and brute-force protections.

Conforms strictly to Architecture Document 07 Sections 1, 2, 3, 4, and 5.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID

from app.core.redis import RedisClient

logger = logging.getLogger(__name__)

# Atomic Monotonic Version Scripts (Architecture Document 07 Section 3.D)
UPDATE_USER_TOKEN_VERSION_LUA = """
local current_ver = redis.call('GET', KEYS[1])
local new_ver = tonumber(ARGV[1])

if not current_ver or tonumber(current_ver) < new_ver then
    redis.call('SET', KEYS[1], new_ver)
    local cursor = "0"
    repeat
        local result = redis.call('SCAN', cursor, 'MATCH', 'session:' .. ARGV[2] .. ':*', 'COUNT', 100)
        cursor = result[1]
        local keys = result[2]
        if #keys > 0 then
            redis.call('DEL', unpack(keys))
        end
    until cursor == "0"
    return 1
else
    return 0
end
"""

UPDATE_ORG_ROLE_VERSION_LUA = """
local current_ver = redis.call('GET', KEYS[1])
local new_ver = tonumber(ARGV[1])

if not current_ver or tonumber(current_ver) < new_ver then
    redis.call('SET', KEYS[1], new_ver)
    local cursor = "0"
    repeat
        local result = redis.call('SCAN', cursor, 'MATCH', 'session:' .. ARGV[3] .. ':*', 'COUNT', 100)
        cursor = result[1]
        local keys = result[2]
        if #keys > 0 then
            redis.call('DEL', unpack(keys))
        end
    until cursor == "0"
    return 1
else
    return 0
end
"""


def get_session_key(user_id: UUID | str, session_id: UUID | str) -> str:
    """Return formatted Redis key for session metadata."""
    return f"session:{user_id}:{session_id}"


def get_user_token_version_key(user_id: UUID | str) -> str:
    """Return formatted Redis key for user token version fence."""
    return f"user_current_token_version:{user_id}"


def get_org_role_version_key(tenant_id: UUID | str, user_id: UUID | str) -> str:
    """Return formatted Redis key for organization membership role version fence."""
    return f"org_current_role_version:{tenant_id}:{user_id}"


async def store_session(
    redis: RedisClient,
    user_id: UUID | str,
    session_id: UUID | str,
    session_data: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Write session metadata to Redis with configured time-to-live."""
    key = get_session_key(user_id, session_id)
    serialized = json.dumps(session_data)
    await redis.set(key, serialized, ex=ttl_seconds)


async def get_session(
    redis: RedisClient,
    user_id: UUID | str,
    session_id: UUID | str,
) -> dict[str, Any] | None:
    """Retrieve session metadata from Redis or return None on cache miss."""
    key = get_session_key(user_id, session_id)
    raw = await redis.get(key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
        return None
    except Exception:
        logger.warning("Corrupted session JSON in Redis for key %s", key)
        return None


async def touch_session_db_verified(
    redis: RedisClient,
    user_id: UUID | str,
    session_id: UUID | str,
    now_timestamp: float,
) -> None:
    """Update last_db_verified_at timestamp in cached session metadata."""
    key = get_session_key(user_id, session_id)
    raw = await redis.get(key)
    if not raw:
        return
    try:
        data = json.loads(raw)
        data["last_db_verified_at"] = now_timestamp
        ttl = await redis.ttl(key)
        if ttl > 0:
            await redis.set(key, json.dumps(data), ex=ttl)
        else:
            await redis.set(key, json.dumps(data))
    except Exception as exc:
        logger.warning("Failed to touch session micro-validation timestamp: %s", exc)


async def delete_session(
    redis: RedisClient,
    user_id: UUID | str,
    session_id: UUID | str,
) -> None:
    """Evict a single session from Redis."""
    key = get_session_key(user_id, session_id)
    await redis.delete(key)


async def delete_all_user_sessions_monotonic(
    redis: RedisClient,
    user_id: UUID | str,
    new_version: int,
) -> bool:
    """Atomically advance user token version fence and evict all user sessions via Lua."""
    fence_key = get_user_token_version_key(user_id)
    res = await redis.eval(  # type: ignore[no-untyped-call]
        UPDATE_USER_TOKEN_VERSION_LUA,
        1,
        fence_key,
        new_version,
        str(user_id),
    )
    return bool(res == 1)


async def update_org_role_version_fence_monotonic(
    redis: RedisClient,
    tenant_id: UUID | str,
    user_id: UUID | str,
    new_version: int,
) -> bool:
    """Atomically advance organization role version fence and evict user sessions via Lua."""
    fence_key = get_org_role_version_key(tenant_id, user_id)
    res = await redis.eval(  # type: ignore[no-untyped-call]
        UPDATE_ORG_ROLE_VERSION_LUA,
        1,
        fence_key,
        new_version,
        str(tenant_id),
        str(user_id),
    )
    return bool(res == 1)


async def get_user_token_version_fence(redis: RedisClient, user_id: UUID | str) -> int | None:
    """Fetch current token version fence for user."""
    key = get_user_token_version_key(user_id)
    val = await redis.get(key)
    return int(val) if val is not None else None


async def get_org_role_version_fence(
    redis: RedisClient, tenant_id: UUID | str, user_id: UUID | str
) -> int | None:
    """Fetch current organization role version fence for membership."""
    key = get_org_role_version_key(tenant_id, user_id)
    val = await redis.get(key)
    return int(val) if val is not None else None


async def set_version_fences_if_absent(
    redis: RedisClient,
    user_id: UUID | str,
    token_version: int,
    tenant_id: UUID | str | None = None,
    role_version: int = 1,
) -> None:
    """Initialize version fences on login if not yet established."""
    user_key = get_user_token_version_key(user_id)
    await redis.set(user_key, token_version)
    if tenant_id:
        role_key = get_org_role_version_key(tenant_id, user_id)
        await redis.set(role_key, role_version)


# ------------------------------------------------------------------------------
# Rate Limiting & Replay Protections
# ------------------------------------------------------------------------------


async def check_rate_limit(
    redis: RedisClient,
    identifier: str,
    action: str = "login",
    max_attempts: int = 5,
    window_seconds: int = 60,
) -> bool:
    """Redis-backed rate limiter for brute-force defense. Returns True if within limit."""
    key = f"rate_limit:{action}:{identifier}"
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    return bool(current <= max_attempts)


async def check_and_record_totp_code(
    redis: RedisClient,
    user_id: UUID | str,
    code: str,
    ttl_seconds: int = 90,
) -> bool:
    """Enforce one-time use of TOTP code within validity window to prevent replay attacks.

    Returns True if code is fresh (not replayed), False if already used.
    """
    key = f"totp_replay:{user_id}:{code.strip()}"
    # SETNX returns 1 if key was set, 0 if it already existed
    is_fresh = await redis.set(key, "1", ex=ttl_seconds, nx=True)
    return bool(is_fresh)
