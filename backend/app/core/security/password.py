"""Password complexity validation, policy enforcement, and compromised password protection.

Enforces enterprise password requirements conforming to Architecture Document 07 and 16.
"""

from __future__ import annotations

import re

from app.core.errors import ValidationException

# Minimum and maximum password lengths
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# Regex patterns for complexity requirements
UPPERCASE_PATTERN = re.compile(r"[A-Z]")
LOWERCASE_PATTERN = re.compile(r"[a-z]")
DIGIT_PATTERN = re.compile(r"[0-9]")
SPECIAL_CHAR_PATTERN = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?`~]""")

# Set of commonly compromised passwords and weak templates (lowercase normalized)
COMMON_PASSWORDS_BLACKLIST: frozenset[str] = frozenset(
    {
        "password1234",
        "password12345",
        "admin1234567",
        "administrator",
        "welcome12345",
        "changeme1234",
        "qwerty123456",
        "letmein12345",
        "iloveyou1234",
        "monkey123456",
        "dragon123456",
        "master123456",
        "sunshine1234",
        "princess1234",
        "football1234",
        "charlie12345",
        "shadow123456",
        "trustno11234",
        "default12345",
        "spring202612",
        "summer202612",
        "winter202612",
        "autumn202612",
        "company12345",
        "recruiter123",
        "candidate123",
    }
)


class PasswordPolicyException(ValidationException):
    """Raised when a candidate password violates enterprise complexity rules."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="ERR_PASSWORD_POLICY_VIOLATION",
            error_code="PASSWORD_POLICY_VIOLATION",
        )


def validate_password_complexity(password: str) -> None:
    """Validate that plaintext password satisfies enterprise length and complexity rules.

    Rules:
    1. Length between 12 and 128 characters.
    2. At least one uppercase letter (A-Z).
    3. At least one lowercase letter (a-z).
    4. At least one numerical digit (0-9).
    5. At least one special symbol.
    6. Cannot match known compromised passwords.
    7. Cannot consist solely of repeated single characters.
    """
    if not isinstance(password, str):
        raise PasswordPolicyException("Password must be a string")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyException(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyException(f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters")

    # Check common compromised blacklist
    normalized = re.sub(r"[^a-zA-Z0-9]", "", password).lower()
    if normalized in COMMON_PASSWORDS_BLACKLIST:
        raise PasswordPolicyException(
            "This password appears in known compromised password lists. Please choose a unique password"
        )

    if not UPPERCASE_PATTERN.search(password):
        raise PasswordPolicyException("Password must contain at least one uppercase letter (A-Z)")

    if not LOWERCASE_PATTERN.search(password):
        raise PasswordPolicyException("Password must contain at least one lowercase letter (a-z)")

    if not DIGIT_PATTERN.search(password):
        raise PasswordPolicyException("Password must contain at least one numerical digit (0-9)")

    if not SPECIAL_CHAR_PATTERN.search(password):
        raise PasswordPolicyException(
            "Password must contain at least one special symbol (!@#$%^&*...)"
        )

    # Check for character variety (e.g. "Aaaaaaaa1!a")
    if len(set(password.lower())) <= 4:
        raise PasswordPolicyException(
            "Password contains too few distinct characters; please choose a more complex password"
        )
