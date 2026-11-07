"""Unit tests for cryptographic foundations: AES-256-GCM, RFC 6238 TOTP, and token security."""

import time

from app.modules.auth.crypto import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_backup_codes,
    generate_csrf_token,
    generate_secure_token,
    generate_totp,
    generate_totp_secret,
    get_totp_uri,
    hash_backup_code,
    hash_token,
    verify_backup_code,
    verify_csrf_token,
    verify_token_hash,
    verify_totp,
)


def test_mfa_secret_aes_256_gcm_round_trip() -> None:
    """Verify AES-256-GCM encryption and decryption round-trip for Tier 1 MFA secrets."""
    secret_key = "a_very_secure_and_long_jwt_secret_key_32_chars_min!"
    plain_secret = generate_totp_secret()

    encrypted = encrypt_mfa_secret(plain_secret, secret_key)
    assert encrypted != plain_secret
    assert len(encrypted) > 20

    decrypted = decrypt_mfa_secret(encrypted, secret_key)
    assert decrypted == plain_secret


def test_rfc6238_totp_generation_and_drift_verification() -> None:
    """Verify RFC 6238 TOTP algorithm, 6-digit formatting, and drift window tolerance."""
    secret = generate_totp_secret()
    now = time.time()

    current_code = generate_totp(secret, timestamp=now)
    assert len(current_code) == 6
    assert current_code.isdigit()

    # Exact current code verifies
    assert verify_totp(secret, current_code) is True

    # Previous 30-second window code verifies with window=1
    prev_code = generate_totp(secret, timestamp=now - 30)
    assert verify_totp(secret, prev_code, window=1) is True

    # Next 30-second window code verifies with window=1
    next_code = generate_totp(secret, timestamp=now + 30)
    assert verify_totp(secret, next_code, window=1) is True

    # Out of window (+90 seconds) code fails
    far_code = generate_totp(secret, timestamp=now + 90)
    assert verify_totp(secret, far_code, window=1) is False

    # Corrupted / invalid codes fail
    assert verify_totp(secret, "000000" if current_code != "000000" else "999999") is False
    assert verify_totp(secret, "abcdef") is False
    assert verify_totp(secret, "123") is False


def test_totp_uri_formatting() -> None:
    """Verify that otpauth URI conforms to authenticator app standards."""
    secret = "JBSWY3DPEHPK3PXP"
    email = "sarah.recruiter@acme-corp.com"
    uri = get_totp_uri(secret, email, issuer="AI HR Platform")

    assert uri.startswith("otpauth://totp/AI%20HR%20Platform:sarah.recruiter%40acme-corp.com")
    assert f"secret={secret}" in uri
    assert "issuer=AI%20HR%20Platform" in uri
    assert "digits=6" in uri


def test_backup_codes_generation_hashing_and_verification() -> None:
    """Verify one-time backup codes generation, hashing, and single-use matching."""
    codes = generate_backup_codes(count=8)
    assert len(codes) == 8
    for c in codes:
        assert len(c) == 9  # e.g., '1A2B-3C4D'
        assert "-" in c

    hashed = [hash_backup_code(c) for c in codes]
    assert len(hashed) == 8

    # Verify first code matches index 0
    idx = verify_backup_code(codes[0], hashed)
    assert idx == 0

    # Case-insensitivity and hyphen-insensitivity
    no_hyphen = codes[1].replace("-", "").lower()
    idx2 = verify_backup_code(no_hyphen, hashed)
    assert idx2 == 1

    # Non-existent code returns -1
    idx_fake = verify_backup_code("ZZZZ-9999", hashed)
    assert idx_fake == -1


def test_secure_tokens_and_csrf() -> None:
    """Verify cryptographic tokens, SHA-256 hashes, and constant-time CSRF matching."""
    token = generate_secure_token(32)
    assert len(token) > 30

    thash = hash_token(token)
    assert verify_token_hash(token, thash) is True
    assert verify_token_hash("tampered_token", thash) is False

    csrf1 = generate_csrf_token()
    csrf2 = generate_csrf_token()
    assert csrf1 != csrf2

    assert verify_csrf_token(csrf1, csrf1) is True
    assert verify_csrf_token(csrf1, csrf2) is False
    assert verify_csrf_token(None, csrf1) is False
    assert verify_csrf_token(csrf1, None) is False
