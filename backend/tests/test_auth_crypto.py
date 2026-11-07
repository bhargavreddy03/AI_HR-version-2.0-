"""Unit tests for cryptographic foundations: AES-256-GCM, RFC 6238 TOTP, and token security."""

import hashlib
import time
import uuid

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
    """Verify AES-256-GCM encryption and decryption round-trip with dedicated MFA encryption key."""
    mfa_key = "a_very_secure_and_long_mfa_encryption_key_32_chars!"
    wrong_key = "another_completely_different_jwt_signing_key_32_ch!"
    plain_secret = generate_totp_secret()

    encrypted = encrypt_mfa_secret(plain_secret, mfa_key)
    assert encrypted != plain_secret
    assert len(encrypted) > 20

    decrypted = decrypt_mfa_secret(encrypted, mfa_key)
    assert decrypted == plain_secret

    # Wrong key fails decryption (authenticated ciphertext integrity check)
    import pytest
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        decrypt_mfa_secret(encrypted, wrong_key)


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
    """Verify 10 one-time backup codes generation, keyed HMAC hashing, and single-use matching."""
    pepper = "a_very_secure_test_backup_code_pepper_32_chars!"
    user_id = uuid.uuid4()
    codes = generate_backup_codes(count=10)
    assert len(codes) == 10
    for c in codes:
        assert len(c) == 9  # e.g., '1A2B-3C4D'
        assert "-" in c

    hashed = [hash_backup_code(c, secret_key=pepper, user_id=user_id) for c in codes]
    assert len(hashed) == 10

    # Verify first code matches index 0
    idx = verify_backup_code(codes[0], hashed, secret_key=pepper, user_id=user_id)
    assert idx == 0

    # Case-insensitivity and hyphen-insensitivity
    no_hyphen = codes[1].replace("-", "").lower()
    idx2 = verify_backup_code(no_hyphen, hashed, secret_key=pepper, user_id=user_id)
    assert idx2 == 1

    # Non-existent code returns -1
    idx_fake = verify_backup_code("ZZZZ-9999", hashed, secret_key=pepper, user_id=user_id)
    assert idx_fake == -1

    # Wrong user_id or secret_key fails matching
    idx_wrong_user = verify_backup_code(codes[0], hashed, secret_key=pepper, user_id=uuid.uuid4())
    assert idx_wrong_user == -1

    idx_wrong_secret = verify_backup_code(
        codes[0], hashed, secret_key="wrong_pepper_key_that_is_32_characters_long!", user_id=user_id
    )
    assert idx_wrong_secret == -1


def test_backup_codes_legacy_hash_migration_fallback() -> None:
    """Verify backward compatibility: legacy unkeyed SHA-256 backup codes are successfully matched."""
    pepper = "a_very_secure_test_backup_code_pepper_32_chars!"
    user_id = uuid.uuid4()
    code = "ABCD-1234"
    clean = "ABCD1234"
    # Legacy hashing scheme using fixed application salt: f"aihr_backup_{clean}"
    legacy_hash = hashlib.sha256(f"aihr_backup_{clean}".encode()).hexdigest()

    hashed_list = ["dummy_hash_0", legacy_hash, "dummy_hash_2"]

    # Verify that verify_backup_code matches legacy hash
    idx = verify_backup_code(code, hashed_list, secret_key=pepper, user_id=user_id)
    assert idx == 1


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
