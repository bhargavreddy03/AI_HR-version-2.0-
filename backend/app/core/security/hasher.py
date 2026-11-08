"""Argon2id password hashing and constant-time verification singleton.

Conforms to Architecture Document 07 and AC-SEC-03 (Argon2id memory >= 64MB).
"""

from __future__ import annotations

import logging

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_hasher: PasswordHasher | None = None


def get_password_hasher(settings: Settings | None = None) -> PasswordHasher:
    """Return configured Argon2id password hasher singleton adhering to AC-SEC-03 (memory >= 64MB)."""
    global _hasher
    if _hasher is None:
        cfg = settings or get_settings()
        _hasher = PasswordHasher(
            time_cost=cfg.ARGON2_TIME_COST,
            memory_cost=cfg.ARGON2_MEMORY_COST,
            parallelism=cfg.ARGON2_PARALLELISM,
            hash_len=cfg.ARGON2_HASH_LEN,
            salt_len=cfg.ARGON2_SALT_LEN,
            type=Type.ID,
        )
    return _hasher


def hash_password(plain_password: str, settings: Settings | None = None) -> str:
    """Hash plaintext password using Argon2id with memory cost >= 64MB."""
    hasher = get_password_hasher(settings=settings)
    return hasher.hash(plain_password)


def verify_password(
    plain_password: str, hashed_password: str, settings: Settings | None = None
) -> bool:
    """Verify plaintext password against stored Argon2id hash using constant-time comparison."""
    hasher = get_password_hasher(settings=settings)
    try:
        return hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str, settings: Settings | None = None) -> bool:
    """Determine whether stored hash parameters have fallen behind current security standards."""
    hasher = get_password_hasher(settings=settings)
    try:
        return hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True
