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

import time
import uuid

from locust import HttpUser, between, task


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
        """Exercise login endpoint: Argon2id password hash computation and Redis rate limiting."""
        payload = {
            "email": f"load-test-{uuid.uuid4().hex[:8]}@enterprise-example.com",
            "password": "WrongPassword123!",
        }
        with self.client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"Content-Type": "application/json"},
            name="/api/v1/auth/login [rate-limit-and-crypto]",
            catch_response=True,
        ) as response:
            if response.status_code in (401, 429):
                # 401: Credential rejected, 429: Rate limit sliding window triggered
                response.success()
            else:
                response.failure(f"Unexpected login response: HTTP {response.status_code}")


# Default user class when invoking locustfile without specifying class name
PlatformLoadTestUser = PlatformSustainedUser
