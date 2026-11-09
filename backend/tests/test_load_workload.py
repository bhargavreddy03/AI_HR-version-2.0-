"""Unit tests for the Locust load-testing workload and account provisioning.

Verifies:
- Idempotent provisioning of dedicated load-test accounts (handling 201 Created and 409 Conflict).
- Resilience against network/connection errors during provisioning.
- Execution of authentication_login_workload targeting existing accounts with Argon2id hash.
- Appropriate handling of HTTP 401 (Argon2id rejected password) and HTTP 429 (Redis rate-limited).
"""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

from tests.load.locustfile import (
    LOAD_TEST_ACCOUNT_EMAIL,
    LOAD_TEST_ACCOUNT_PASSWORD,
    LOAD_TEST_ACCOUNT_POOL,
    LOAD_TEST_INVALID_PASSWORD,
    PlatformSustainedUser,
    provision_load_test_accounts,
)


def test_load_test_account_constants_validity() -> None:
    assert "@" in LOAD_TEST_ACCOUNT_EMAIL
    assert len(LOAD_TEST_ACCOUNT_POOL) > 0
    for email in LOAD_TEST_ACCOUNT_POOL:
        assert "@" in email
        assert email.endswith("@platform.local")
    assert len(LOAD_TEST_ACCOUNT_PASSWORD) >= 12
    assert len(LOAD_TEST_INVALID_PASSWORD) >= 12


def test_provision_load_test_accounts_idempotent() -> None:
    # Scenario 1: First account returns 201 (Created), others return 409 (Already exists)
    mock_resp_201 = MagicMock()
    mock_resp_201.status = 201

    def side_effect(req, timeout):
        # Account 0 created, rest already exist
        if LOAD_TEST_ACCOUNT_EMAIL.encode() in req.data:
            return mock_resp_201
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=409,
            msg="Conflict",
            hdrs={},
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=side_effect):
        # Should complete gracefully without raising
        provision_load_test_accounts("http://127.0.0.1:8000")


def test_provision_load_test_accounts_handles_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        # Must catch and log gracefully, not crash
        provision_load_test_accounts("http://127.0.0.1:8000")


def test_sustained_user_login_workload_401_success() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_context.__exit__.return_value = None
    mock_client.post.return_value = mock_context

    sustained_user = PlatformSustainedUser(environment=MagicMock())
    sustained_user.client = mock_client

    sustained_user.authentication_login_workload()

    mock_client.post.assert_called_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert call_args[0] == "/api/v1/auth/login"
    assert call_kwargs["json"]["password"] == LOAD_TEST_INVALID_PASSWORD
    assert (
        call_kwargs["json"]["email"] == LOAD_TEST_ACCOUNT_EMAIL
        or call_kwargs["json"]["email"] in LOAD_TEST_ACCOUNT_POOL
    )
    mock_response.success.assert_called_once()


def test_sustained_user_login_workload_429_success() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_context.__exit__.return_value = None
    mock_client.post.return_value = mock_context

    sustained_user = PlatformSustainedUser(environment=MagicMock())
    sustained_user.client = mock_client

    sustained_user.authentication_login_workload()
    mock_response.success.assert_called_once()


def test_sustained_user_login_workload_unexpected_failure() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_context.__exit__.return_value = None
    mock_client.post.return_value = mock_context

    sustained_user = PlatformSustainedUser(environment=MagicMock())
    sustained_user.client = mock_client

    sustained_user.authentication_login_workload()
    mock_response.failure.assert_called_once()
