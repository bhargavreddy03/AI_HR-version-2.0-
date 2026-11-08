"""Application-level authenticated encryption at rest using AES-256-GCM and HKDF-SHA256.

Enforces Tier 1 and Tier 2 data classification protection conforming to Architecture Document 16 Section 1.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_field_encryption_key(
    master_key: str | bytes,
    context_info: str = "aihr_field_encryption",
    salt: bytes = b"aihr_application_field_encryption_salt",
) -> bytes:
    """Derive an isolated 256-bit symmetric encryption key using HKDF-SHA256."""
    raw_key = master_key.encode("utf-8") if isinstance(master_key, str) else master_key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=context_info.encode("utf-8"),
    )
    return hkdf.derive(raw_key)


def encrypt_sensitive_data(
    plaintext: str | bytes,
    master_key: str | bytes,
    context_info: str = "aihr_field_encryption",
) -> str:
    """Encrypt plaintext string or bytes using AES-256-GCM with a cryptographically random 96-bit nonce.

    Returns:
        Base64-encoded string concatenation of (12-byte nonce + ciphertext + 16-byte authentication tag).
    """
    key = derive_field_encryption_key(master_key, context_info=context_info)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_sensitive_data(
    encrypted_payload: str,
    master_key: str | bytes,
    context_info: str = "aihr_field_encryption",
) -> str:
    """Decrypt base64-encoded nonce+ciphertext payload using AES-256-GCM with authentication tag verification.

    Raises:
        ValueError: If ciphertext has been tampered with, truncated, or encrypted with a different key.
    """
    key = derive_field_encryption_key(master_key, context_info=context_info)
    raw = base64.b64decode(encrypted_payload)
    if len(raw) < 28:  # 12-byte nonce + 16-byte tag minimum
        raise ValueError("Invalid encrypted payload: too short for AES-256-GCM")
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext_bytes.decode("utf-8")
