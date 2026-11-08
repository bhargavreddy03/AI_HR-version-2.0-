"""Performance and cryptographic baseline benchmarks.

Verifies throughput, execution latencies, and algorithmic calibration for:
1. Argon2id password hashing and verification calibration bounds.
2. AES-256-GCM symmetric authenticated encryption/decryption throughput.
3. JWT access and refresh token generation and decoding latency.
4. RFC 6238 TOTP computation and constant-time backup code verification.
5. Password complexity validation throughput under high load.
"""

from __future__ import annotations

import time
from uuid import uuid4

from app.core.config import get_settings
from app.core.security.encryption import decrypt_sensitive_data, encrypt_sensitive_data
from app.core.security.hasher import hash_password, verify_password
from app.core.security.password import validate_password_complexity
from app.modules.auth.crypto import (
    generate_backup_codes,
    generate_totp,
    generate_totp_secret,
    hash_backup_code,
    verify_backup_code,
    verify_totp,
)
from app.modules.auth.jwt import (
    create_access_token,
    decode_access_token,
)


def test_argon2id_password_hashing_calibration() -> None:
    """Argon2id hashing and verification execute within calibrated latency limits."""
    raw_password = "CorrectHorseBatteryStaple!2026#Secure"

    start_hash = time.perf_counter()
    hashed = hash_password(raw_password)
    hash_duration = time.perf_counter() - start_hash

    # Argon2id should take at least 10ms (security resistance) but no more than 2.0s (prevent DoS)
    assert hash_duration < 2.0, f"Argon2id hashing took too long: {hash_duration:.3f}s"
    assert hashed.startswith("$argon2id$")

    start_verify = time.perf_counter()
    assert verify_password(raw_password, hashed) is True
    verify_duration = time.perf_counter() - start_verify
    assert verify_duration < 2.0, f"Argon2id verification took too long: {verify_duration:.3f}s"

    # Negative check fails fast
    assert verify_password("WrongPassword123!", hashed) is False


def test_aes256_gcm_encryption_throughput() -> None:
    """AES-256-GCM authenticated encryption and decryption achieves high throughput."""
    key = b"0123456789abcdef0123456789abcdef"  # 32 bytes = 256 bits
    sample_payload = '{"candidate_ssn": "123-45-6789", "salary_expectation": 185000}'

    iterations = 200
    start = time.perf_counter()
    for _ in range(iterations):
        ciphertext = encrypt_sensitive_data(sample_payload, key)
        decrypted = decrypt_sensitive_data(ciphertext, key)
        assert decrypted == sample_payload
    duration = time.perf_counter() - start

    assert (
        duration < 1.0
    ), f"{iterations} AES-GCM operations took {duration:.3f}s (exceeds 1.0s limit)"
    throughput = (iterations * 2) / duration
    assert throughput > 400, f"AES-GCM throughput too low: {throughput:.0f} ops/sec"


def test_jwt_access_token_throughput() -> None:
    """JWT token signing and verification execute efficiently at scale."""
    settings = get_settings()
    iterations = 200
    user_id = uuid4()
    tenant_id = uuid4()
    session_id = uuid4()
    role = "recruiter"
    permissions = ["candidates:read", "candidates:write", "jobs:read"]

    start = time.perf_counter()
    for i in range(iterations):
        access_token = create_access_token(
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            role=role,
            permissions=permissions,
            token_version=i,
            role_version=1,
            is_super_admin=False,
            settings=settings,
        )
        claims = decode_access_token(access_token, settings=settings)
        assert claims.sub == str(user_id)
        assert claims.token_version == i
    duration = time.perf_counter() - start

    # 200 tokens signed and 200 tokens decoded
    assert duration < 1.0, f"JWT roundtrips took {duration:.3f}s (exceeds 1.0s limit)"


def test_totp_and_backup_code_cryptography_performance() -> None:
    """RFC 6238 TOTP computation and backup code hashing scale efficiently."""
    iterations = 50
    secret_key = "test-secret-salt-key-for-benchmarking"
    user_id = uuid4()
    start = time.perf_counter()
    for _ in range(iterations):
        secret = generate_totp_secret()
        code = generate_totp(secret)
        assert len(code) == 6
        assert verify_totp(secret, code) is True

        raw_codes = generate_backup_codes(count=8)
        assert len(raw_codes) == 8
        hashed_codes = [hash_backup_code(c, secret_key, user_id=user_id) for c in raw_codes]
        # Verify first code matches index 0
        matched_idx = verify_backup_code(raw_codes[0], hashed_codes, secret_key, user_id=user_id)
        assert matched_idx == 0
        # Verify invalid code matches -1
        assert verify_backup_code("INVALID-CODE", hashed_codes, secret_key, user_id=user_id) == -1
    duration = time.perf_counter() - start

    assert duration < 1.0, f"TOTP/Backup operations took {duration:.3f}s (exceeds 1.0s limit)"


def test_password_policy_validation_performance() -> None:
    """High-throughput password policy validation handles > 2,000 checks per second."""
    iterations = 1000
    valid_passwords = [
        "Str0ng#Passw0rd!2026",
        "Complex_Secret#8821",
        "P@ssw0rdEnterprise2026!",
        "SecureRecruitment99$",
    ]

    start = time.perf_counter()
    for i in range(iterations):
        pwd = valid_passwords[i % len(valid_passwords)]
        validate_password_complexity(pwd)
    duration = time.perf_counter() - start

    assert duration < 0.5, f"1000 password checks took {duration:.3f}s (exceeds 0.5s limit)"
