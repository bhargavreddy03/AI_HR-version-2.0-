"""Performance, load, and cryptographic baseline benchmarks.

Verifies throughput, execution latencies, and algorithmic calibration for:
1. Argon2id password hashing calibration (per AC-SEC-03: memory_cost=64MB, time_cost=3, parallelism=4).
2. AES-256-GCM symmetric authenticated encryption/decryption throughput.
3. JWT access token generation and decoding latency.
4. RFC 6238 TOTP computation and constant-time backup code verification.
5. Concurrent API health probe throughput under simulated multi-user load.
6. Password complexity validation throughput under sustained load.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.security.encryption import decrypt_sensitive_data, encrypt_sensitive_data
from app.core.security.hasher import hash_password, verify_password
from app.core.security.password import validate_password_complexity
from app.main import app
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
    """Argon2id hashing and verification execute within calibrated AC-SEC-03 enterprise parameters.

    Calibration verifies:
    - Algorithm type is Argon2id with 64MB (65536 KB) memory cost, time cost 3, parallelism 4.
    - Resulting hash prefix strictly conforms to $argon2id$v=19$m=65536,t=3,p=4$.
    - Constant-time verification strictly distinguishes valid vs invalid passwords.
    - Algorithmic execution completes within safe upper bounds avoiding DoS vulnerabilities.
    """
    raw_password = "CorrectHorseBatteryStaple!2026#Secure"

    start_hash = time.perf_counter()
    hashed = hash_password(raw_password)
    hash_duration = time.perf_counter() - start_hash

    # Argon2id format must adhere to AC-SEC-03 specification: memory=65536, time=3, parallelism=4
    assert hashed.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in hashed
    # Generous safety upper bound (prevents DoS without being machine-dependent or flaky on CI VMs)
    assert hash_duration < 10.0, f"Argon2id hashing took excessively long: {hash_duration:.3f}s"

    start_verify = time.perf_counter()
    assert verify_password(raw_password, hashed) is True
    verify_duration = time.perf_counter() - start_verify
    assert (
        verify_duration < 10.0
    ), f"Argon2id verification took excessively long: {verify_duration:.3f}s"

    # Verification against incorrect credentials must fail cleanly
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

    # Asserts 200 roundtrips complete reliably without deadlock or failure
    assert duration < 5.0, f"{iterations} AES-GCM operations took {duration:.3f}s"
    throughput = (iterations * 2) / max(duration, 0.001)
    assert throughput > 100, f"AES-GCM throughput unexpectedly low: {throughput:.0f} ops/sec"


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

    assert duration < 5.0, f"JWT roundtrips took {duration:.3f}s"


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
        matched_idx = verify_backup_code(raw_codes[0], hashed_codes, secret_key, user_id=user_id)
        assert matched_idx == 0
        assert verify_backup_code("INVALID-CODE", hashed_codes, secret_key, user_id=user_id) == -1
    duration = time.perf_counter() - start

    assert duration < 5.0, f"TOTP/Backup operations took {duration:.3f}s"


def test_password_policy_validation_performance() -> None:
    """High-throughput password policy validation handles bulk evaluations."""
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

    assert duration < 3.0, f"1000 password checks took {duration:.3f}s"


@pytest.mark.asyncio
async def test_concurrent_api_health_load() -> None:
    """FastAPI application handles concurrent load on liveness probes without contention."""
    concurrent_requests = 50
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_time = time.perf_counter()
        tasks = [client.get("/api/v1/health") for _ in range(concurrent_requests)]
        responses = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start_time

    assert len(responses) == concurrent_requests
    for resp in responses:
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    # All 50 concurrent requests should complete within a reasonable window
    assert elapsed < 5.0, f"50 concurrent health checks took {elapsed:.3f}s"
