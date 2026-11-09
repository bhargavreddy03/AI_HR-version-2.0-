"""Unit tests for the Locust load-testing workload and account provisioning.

Verifies:
- Idempotent provisioning of dedicated load-test accounts (handling HTTP 201 Created and HTTP 409 Conflict).
- Rigorous failure detection: HTTP errors, network failures, and incomplete provisioning abort with RuntimeError.
- Redundant account provisioning is completely removed from virtual-user on_start() calls.
- Argon2id login workload is halted if account provisioning has not succeeded.
- Execution of authentication_login_workload targeting existing accounts with Argon2id hash.
- Appropriate handling of HTTP 401 (Argon2id rejected password) and HTTP 429 (Redis rate-limited).
"""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import tests.load.locustfile as locust_module
from tests.load.locustfile import (
    LOAD_TEST_ACCOUNT_EMAIL,
    LOAD_TEST_ACCOUNT_PASSWORD,
    LOAD_TEST_ACCOUNT_POOL,
    LOAD_TEST_INVALID_PASSWORD,
    PlatformSustainedUser,
    on_test_start,
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


def test_redundant_on_start_removed_from_sustained_user() -> None:
    """Verify that redundant account provisioning is removed from virtual user on_start()."""
    # PlatformSustainedUser must not define an on_start that provisions accounts
    if hasattr(PlatformSustainedUser, "on_start"):
        import inspect

        src = inspect.getsource(PlatformSustainedUser.on_start)
        assert "provision_load_test_accounts" not in src


def test_provision_load_test_accounts_http_201_success() -> None:
    """Verify clean setup when all accounts are freshly created (HTTP 201)."""
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value.status = 201

    with patch("urllib.request.urlopen", return_value=mock_cm):
        success = provision_load_test_accounts("http://127.0.0.1:8000")
        assert success is True
        assert locust_module.PROVISIONING_SUCCEEDED is True


def test_provision_load_test_accounts_http_409_idempotent_success() -> None:
    """Verify idempotent setup when all accounts already exist (HTTP 409 Conflict)."""

    def side_effect(req, timeout):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=409,
            msg="Conflict",
            hdrs={},
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=side_effect):
        success = provision_load_test_accounts("http://127.0.0.1:8000")
        assert success is True
        assert locust_module.PROVISIONING_SUCCEEDED is True


def test_provision_load_test_accounts_mixed_201_and_409_success() -> None:
    """Verify idempotent setup when some accounts return 201 and some return 409."""
    mock_cm_201 = MagicMock()
    mock_cm_201.__enter__.return_value.status = 201

    def side_effect(req, timeout):
        if LOAD_TEST_ACCOUNT_EMAIL.encode() in req.data:
            return mock_cm_201
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=409,
            msg="Conflict",
            hdrs={},
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=side_effect):
        success = provision_load_test_accounts("http://127.0.0.1:8000")
        assert success is True
        assert locust_module.PROVISIONING_SUCCEEDED is True


def test_provision_load_test_accounts_unexpected_http_status_fails() -> None:
    """Verify setup failure when registration returns unexpected status code (e.g. 500)."""
    mock_cm_500 = MagicMock()
    mock_cm_500.__enter__.return_value.status = 500

    with patch("urllib.request.urlopen", return_value=mock_cm_500):
        with pytest.raises(RuntimeError, match="Setup failure: Unexpected HTTP 500"):
            provision_load_test_accounts("http://127.0.0.1:8000")
        assert locust_module.PROVISIONING_SUCCEEDED is False


def test_provision_load_test_accounts_http_error_fails() -> None:
    """Verify setup failure when registration returns HTTP error (e.g. 400 Bad Request)."""

    def side_effect(req, timeout):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with pytest.raises(RuntimeError, match="Setup failure: HTTP error 400"):
            provision_load_test_accounts("http://127.0.0.1:8000")
        assert locust_module.PROVISIONING_SUCCEEDED is False


def test_provision_load_test_accounts_network_failure_fails() -> None:
    """Verify setup failure when network connection fails."""
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        with pytest.raises(RuntimeError, match="Setup failure: Network error"):
            provision_load_test_accounts("http://127.0.0.1:8000")
        assert locust_module.PROVISIONING_SUCCEEDED is False


def test_provision_load_test_accounts_incomplete_provisioning_fails() -> None:
    """Verify setup failure if not all required accounts are verified."""
    mock_resp_201 = MagicMock()
    mock_resp_201.status = 201

    call_count = 0

    def side_effect(req, timeout):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return mock_resp_201
        raise OSError("Transient failure on account 3")

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with pytest.raises(RuntimeError):
            provision_load_test_accounts("http://127.0.0.1:8000")
        assert locust_module.PROVISIONING_SUCCEEDED is False


def test_on_test_start_listener_quits_runner_on_failure() -> None:
    """Verify on_test_start event listener signals runner to quit on setup failure."""
    mock_env = MagicMock()
    mock_env.host = "http://127.0.0.1:8000"
    mock_env.runner = MagicMock()

    with patch(
        "tests.load.locustfile.provision_load_test_accounts",
        side_effect=RuntimeError("DB unreachable"),
    ):
        with pytest.raises(RuntimeError, match="DB unreachable"):
            on_test_start(mock_env)
        mock_env.runner.quit.assert_called_once()


def test_sustained_user_login_workload_refuses_when_unprovisioned() -> None:
    """Verify Argon2id workload does not start if provisioning has not succeeded."""
    locust_module.PROVISIONING_SUCCEEDED = False

    mock_client = MagicMock()
    sustained_user = PlatformSustainedUser(environment=MagicMock())
    sustained_user.client = mock_client

    with pytest.raises(RuntimeError, match="Cannot execute Argon2id workload"):
        sustained_user.authentication_login_workload()

    mock_client.post.assert_not_called()


def test_sustained_user_login_workload_401_success() -> None:
    """Verify 401 response counts as success when provisioning succeeded."""
    locust_module.PROVISIONING_SUCCEEDED = True

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
    """Verify 429 response counts as success when provisioning succeeded."""
    locust_module.PROVISIONING_SUCCEEDED = True

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
    """Verify unexpected HTTP status marks response as failure."""
    locust_module.PROVISIONING_SUCCEEDED = True

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
