"""Cryptographic utilities: AES-256-GCM MFA secret encryption, RFC 6238 TOTP, and secure tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from typing import TYPE_CHECKING
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

if TYPE_CHECKING:
    pass


# ------------------------------------------------------------------------------
# 1. AES-256-GCM MFA Secret Encryption at Rest (Data Classification Tier 1)
# ------------------------------------------------------------------------------


def derive_aes_key(mfa_encryption_key: str | bytes) -> bytes:
    """Derive 256-bit encryption key using HKDF-SHA256 from dedicated MFA encryption key."""
    raw_key = (
        mfa_encryption_key.encode("utf-8")
        if isinstance(mfa_encryption_key, str)
        else mfa_encryption_key
    )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"aihr_dedicated_mfa_encryption_salt",
        info=b"aihr_mfa_aes256gcm_isolated",
    )
    return hkdf.derive(raw_key)


def encrypt_mfa_secret(secret_base32: str, mfa_encryption_key: str | bytes) -> str:
    """Encrypt plaintext base32 TOTP secret using AES-256-GCM with a random 96-bit nonce."""
    key = derive_aes_key(mfa_encryption_key)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, secret_base32.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_mfa_secret(encrypted_secret: str, mfa_encryption_key: str | bytes) -> str:
    """Decrypt base64-encoded nonce+ciphertext payload using AES-256-GCM."""
    key = derive_aes_key(mfa_encryption_key)
    raw = base64.b64decode(encrypted_secret)
    if len(raw) < 12:
        raise ValueError("Invalid encrypted MFA payload length")
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ------------------------------------------------------------------------------
# 2. RFC 6238 TOTP Implementation
# ------------------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Generate a cryptographically random 160-bit (20-byte) base32 encoded TOTP secret."""
    return base64.b32encode(os.urandom(20)).decode("utf-8")


def generate_totp(
    secret_base32: str,
    timestamp: float | None = None,
    interval: int = 30,
    digits: int = 6,
) -> str:
    """Generate RFC 6238 time-based one-time password."""
    t = int((timestamp or time.time()) // interval)
    key = base64.b32decode(secret_base32, casefold=True)
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def verify_totp(
    secret_base32: str,
    code: str,
    window: int = 1,
    interval: int = 30,
    digits: int = 6,
) -> bool:
    """Verify TOTP code within a drift tolerance window (default +/- 1 step = 30 seconds)."""
    clean_code = str(code).strip()
    if len(clean_code) != digits or not clean_code.isdigit():
        return False

    now = time.time()
    for step in range(-window, window + 1):
        expected = generate_totp(
            secret_base32, timestamp=now + (step * interval), interval=interval, digits=digits
        )
        if hmac.compare_digest(clean_code, expected):
            return True
    return False


def get_totp_uri(secret_base32: str, email: str, issuer: str = "AI HR Platform") -> str:
    """Build standard otpauth:// URI for authenticator app enrollment."""
    from urllib.parse import quote

    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={secret_base32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


# ------------------------------------------------------------------------------
# 3. MFA Backup Codes
# ------------------------------------------------------------------------------


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate high-entropy one-time backup codes (e.g., 'A1B2-C3D4')."""
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        codes.append(formatted)
    return codes


def hash_backup_code(
    code: str,
    secret_key: str | bytes,
    user_id: UUID | str | None = None,
) -> str:
    """Hash single backup code using HMAC-SHA256 with dedicated server secret and user salt.

    Never stores the pepper/key in PostgreSQL.
    """
    clean = code.strip().upper().replace("-", "")
    key_bytes = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    msg = f"{user_id}:{clean}".encode() if user_id else clean.encode("utf-8")
    return hmac.new(key_bytes, msg, hashlib.sha256).hexdigest()


def verify_backup_code(
    code: str,
    hashed_codes: list[str],
    secret_key: str | bytes,
    user_id: UUID | str | None = None,
) -> int:
    """Verify backup code against list of stored hashes in constant time.

    Supports modern per-user keyed HMAC hashes and falls back to legacy fixed-salt SHA-256 for migration.
    Returns the index of the matching code, or -1 if not found.
    """
    clean = code.strip().upper().replace("-", "")
    modern_hash = hash_backup_code(clean, secret_key=secret_key, user_id=user_id)

    # 1. Constant-time check against modern keyed HMAC
    matched_idx = -1
    for idx, stored in enumerate(hashed_codes):
        if hmac.compare_digest(modern_hash, stored):
            matched_idx = idx
            break

    if matched_idx != -1:
        return matched_idx

    # 2. Migration fallback: check legacy fixed-salt hash for backward compatibility
    legacy_hash = hashlib.sha256(f"aihr_backup_{clean}".encode()).hexdigest()
    for idx, stored in enumerate(hashed_codes):
        if hmac.compare_digest(legacy_hash, stored):
            return idx

    return -1


# ------------------------------------------------------------------------------
# 4. Cryptographic Random Tokens & CSRF
# ------------------------------------------------------------------------------


def generate_secure_token(length_bytes: int = 32) -> str:
    """Generate URL-safe cryptographically secure random token string."""
    return secrets.token_urlsafe(length_bytes)


def hash_token(token: str) -> str:
    """Compute constant-time verifiable SHA-256 hash of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token_hash(token: str, stored_hash: str) -> bool:
    """Verify plaintext token against stored SHA-256 hash in constant time."""
    computed = hash_token(token)
    return hmac.compare_digest(computed, stored_hash)


def generate_csrf_token() -> str:
    """Generate random 32-byte hex CSRF token for aihr_csrf cookie and header."""
    return secrets.token_hex(32)


def verify_csrf_token(header_token: str | None, cookie_token: str | None) -> bool:
    """Constant-time verification of X-CSRF-Token header against aihr_csrf cookie."""
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token.strip(), cookie_token.strip())
