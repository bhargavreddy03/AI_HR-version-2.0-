"""Locust performance and load testing suite for the AI HR Intelligence Platform.

Provides dual profiles:
1. PlatformSmokeUser: Short smoke verification for CI container startup validation.
2. PlatformSustainedUser: Realistic sustained enterprise workload exercising:
   - Deep PostgreSQL and Redis dependency readiness under concurrency.
   - Distributed Celery task dispatching, queue routing, and result polling.
   - Authentication perimeter, Argon2id verification, and sliding-window rate limiting.
   - OpenAPI 3.1 specification discovery.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

try:
    from locust import HttpUser, between, events, task
except ImportError:  # pragma: no cover
    # Fallback definitions when locust package is not present in runner environment
    class HttpUser:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.client: Any = None

    def between(min_v: float, max_v: float) -> Any:  # type: ignore[misc]
        return lambda: min_v

    def task(weight: int = 1) -> Any:  # type: ignore[misc]
        return lambda fn: fn

    class _Events:
        class _EventHook:
            def add_listener(self, fn: Any) -> Any:
                return fn

        test_start = _EventHook()

    events = _Events()  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Dedicated, isolated load-test account configuration
LOAD_TEST_ACCOUNT_EMAIL = "loadtest.worker@platform.local"
LOAD_TEST_ACCOUNT_PASSWORD = "LoadTestPassword2026!#"
LOAD_TEST_INVALID_PASSWORD = "IntentionallyIncorrectPassword123!"

# Pool of deterministic load-test worker accounts to exercise concurrent Argon2id hashing
LOAD_TEST_ACCOUNT_POOL = [f"loadtest.worker.{i}@platform.local" for i in range(5)]


def provision_load_test_accounts(host: str) -> None:
    """Ensure dedicated, isolated load-test accounts exist in the database with valid Argon2id hashes.

    Uses the standard public registration endpoint (/api/v1/auth/register).
    Deterministic email addresses prevent uncontrolled duplicate account creation across test runs.
    - HTTP 201: Account created with fresh Argon2id hash.
    - HTTP 409: Account already exists from a prior test run (expected on repeated runs).
    """
    clean_host = host.rstrip("/")
    all_accounts = [LOAD_TEST_ACCOUNT_EMAIL, *LOAD_TEST_ACCOUNT_POOL]
    for email in all_accounts:
        payload = json.dumps(
            {
                "email": email,
                "password": LOAD_TEST_ACCOUNT_PASSWORD,
                "first_name": "Load",
                "last_name": "Tester",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{clean_host}/api/v1/auth/register",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LocustSetup/2.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 201:
                    logger.info("Successfully provisioned load-test account: %s", email)
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                # 409 Conflict: Account already exists with valid Argon2id hash
                pass
            else:
                logger.warning("Provisioning returned HTTP %d for %s", exc.code, email)
        except Exception as exc:
            logger.debug("Could not reach host to provision %s: %s", email, exc)


@events.test_start.add_listener
def on_test_start(environment: Any, **kwargs: Any) -> None:
    """Pre-provision dedicated load-test accounts when Locust test begins."""
    host = environment.host or "http://127.0.0.1:8000"
    provision_load_test_accounts(host)


class PlatformSmokeUser(HttpUser):
    """Lightweight smoke load profile for CI validation."""

    wait_time = between(0.1, 0.5)

    @task(3)
    def liveness_smoke(self) -> None:
        self.client.get("/api/v1/health/liveness", name="/api/v1/health/liveness [smoke]")

    @task(2)
    def readiness_smoke(self) -> None:
        self.client.get("/api/v1/health/ready", name="/api/v1/health/ready [smoke]")

    @task(1)
    def task_ping_smoke(self) -> None:
        self.client.post(
            "/api/v1/tasks/system/ping",
            json={"message": "smoke-ping"},
            headers={"Content-Type": "application/json"},
            name="/api/v1/tasks/system/ping [smoke]",
        )


class PlatformSustainedUser(HttpUser):
    """Realistic sustained multi-user enterprise workload profile."""

    wait_time = between(0.05, 0.25)

    def on_start(self) -> None:
        """Ensure load-test accounts exist for this virtual user session."""
        base_url = getattr(self.client, "base_url", None) or "http://127.0.0.1:8000"
        provision_load_test_accounts(base_url)

    @task(5)
    def liveness_check(self) -> None:
        """Sustained liveness verification under concurrent throughput."""
        with self.client.get(
            "/api/v1/health/liveness",
            name="/api/v1/health/liveness",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Liveness failed: HTTP {response.status_code}")

    @task(4)
    def deep_readiness_probe(self) -> None:
        """Deep readiness probe exercising PostgreSQL pool checkout and Redis ping."""
        with self.client.get(
            "/api/v1/health/ready",
            name="/api/v1/health/ready",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("database") == "connected" and data.get("redis") == "connected":
                    response.success()
                else:
                    response.failure(f"Dependencies degraded: {data}")
            else:
                response.failure(f"Readiness probe failed: HTTP {response.status_code}")

    @task(2)
    def openapi_schema_discovery(self) -> None:
        """Fetch OpenAPI 3.1 specification schema under concurrency."""
        with self.client.get(
            "/api/v1/openapi.json",
            name="/api/v1/openapi.json",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"OpenAPI schema retrieval failed: HTTP {response.status_code}")

    @task(3)
    def submit_and_poll_celery_task(self) -> None:
        """Exercise Celery worker dispatching, Redis broker idempotency, and result polling."""
        payload = {"message": f"sustained-load-{uuid.uuid4().hex[:12]}"}
        with self.client.post(
            "/api/v1/tasks/system/ping",
            json=payload,
            headers={"Content-Type": "application/json"},
            name="/api/v1/tasks/system/ping",
            catch_response=True,
        ) as submit_res:
            if submit_res.status_code in (200, 202):
                submit_res.success()
                task_data = submit_res.json()
                task_id = task_data.get("task_id")
                if task_id:
                    # Poll status up to 3 times to observe asynchronous worker progression
                    for _ in range(3):
                        time.sleep(0.05)
                        self.client.get(
                            f"/api/v1/tasks/{task_id}/status",
                            name="/api/v1/tasks/[task_id]/status",
                        )
            else:
                submit_res.failure(f"Task dispatch failed: HTTP {submit_res.status_code}")

    @task(2)
    def unauthenticated_perimeter_defense(self) -> None:
        """Verify protected authentication dependencies reject unauthenticated calls with HTTP 401."""
        with self.client.get(
            "/api/v1/auth/me",
            name="/api/v1/auth/me [perimeter-defense]",
            catch_response=True,
        ) as response:
            if response.status_code == 401:
                response.success()
            else:
                response.failure(f"Expected HTTP 401 unauthorized, got {response.status_code}")

    @task(2)
    def authentication_login_workload(self) -> None:
        """Exercise login endpoint: Real Argon2id password hash computation and Redis rate limiting.

        Targets an existing load-test account with an intentionally incorrect password.
        Because the account exists in PostgreSQL, the authentication service executes
        verify_password() (full Argon2id computation) before rejecting the credentials.
        Under sustained concurrency, requests beyond the sliding-window threshold exercise
        Redis rate limiting (HTTP 429).
        """
        target_email = random.choice([LOAD_TEST_ACCOUNT_EMAIL, *LOAD_TEST_ACCOUNT_POOL])
        payload = {
            "email": target_email,
            "password": LOAD_TEST_INVALID_PASSWORD,
        }
        with self.client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"Content-Type": "application/json"},
            name="/api/v1/auth/login [argon2id-and-rate-limit]",
            catch_response=True,
        ) as response:
            if response.status_code in (401, 429):
                # 401: Argon2id verification executed & rejected incorrect password
                # 429: Redis sliding-window brute-force rate limit triggered under load
                response.success()
            else:
                response.failure(f"Unexpected login response: HTTP {response.status_code}")


# Default user class when invoking locustfile without specifying class name
PlatformLoadTestUser = PlatformSustainedUser
