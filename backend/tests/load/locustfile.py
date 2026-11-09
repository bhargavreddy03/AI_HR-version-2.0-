"""Locust performance and load testing suite for the AI HR Intelligence Platform.

Simulates concurrent user load against actual running backend services:
1. High-frequency liveness and readiness probe verification.
2. OpenAPI 3.1 specification schema queries.
3. Background task submission and asynchronous polling.
4. Unauthenticated resource rejection and security perimeter enforcement.
5. Invalid credential rejection under concurrency.
"""

from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class PlatformLoadTestUser(HttpUser):
    """Simulates realistic enterprise platform traffic under concurrent multi-user load."""

    wait_time = between(0.05, 0.25)

    @task(6)
    def liveness_check(self) -> None:
        """Sustained liveness verification under concurrency."""
        with self.client.get(
            "/api/v1/health/liveness",
            name="/api/v1/health/liveness",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Liveness probe failed with HTTP {response.status_code}")

    @task(4)
    def readiness_check(self) -> None:
        """Deep readiness probe verifying PostgreSQL and Redis health under concurrency."""
        with self.client.get(
            "/api/v1/health/ready",
            name="/api/v1/health/ready",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Readiness probe failed with HTTP {response.status_code}")

    @task(2)
    def openapi_schema_discovery(self) -> None:
        """Fetch OpenAPI 3.1 schema specification."""
        with self.client.get(
            "/api/v1/openapi.json",
            name="/api/v1/openapi.json",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(
                    f"OpenAPI schema retrieval failed with HTTP {response.status_code}"
                )

    @task(3)
    def submit_and_poll_diagnostic_task(self) -> None:
        """Simulate distributed Celery task dispatch and subsequent status polling."""
        task_payload = {"message": f"load-test-ping-{uuid.uuid4()}"}
        with self.client.post(
            "/api/v1/tasks/system/ping",
            json=task_payload,
            headers={"Content-Type": "application/json"},
            name="/api/v1/tasks/system/ping",
            catch_response=True,
        ) as submit_res:
            if submit_res.status_code in (200, 202):
                submit_res.success()
                data = submit_res.json()
                task_id = data.get("task_id")
                if task_id:
                    self.client.get(
                        f"/api/v1/tasks/{task_id}/status",
                        name="/api/v1/tasks/[task_id]/status",
                    )
            else:
                submit_res.failure(f"Task dispatch failed with HTTP {submit_res.status_code}")

    @task(2)
    def unauthenticated_security_perimeter_rejection(self) -> None:
        """Verify protected endpoints enforce HTTP 401 under concurrency."""
        with self.client.get(
            "/api/v1/auth/me",
            name="/api/v1/auth/me [expected-401]",
            catch_response=True,
        ) as response:
            if response.status_code == 401:
                response.success()
            else:
                response.failure(
                    f"Expected HTTP 401 unauthorized, received HTTP {response.status_code}"
                )

    @task(1)
    def invalid_credentials_auth_rejection(self) -> None:
        """Verify password authentication rejects bogus credentials with HTTP 401 under load."""
        login_payload = {
            "email": f"nonexistent-{uuid.uuid4().hex[:8]}@enterprise-loadtest.com",
            "password": "WrongPassword999!",
        }
        with self.client.post(
            "/api/v1/auth/login",
            json=login_payload,
            headers={"Content-Type": "application/json"},
            name="/api/v1/auth/login [expected-401]",
            catch_response=True,
        ) as response:
            if response.status_code in (401, 429):
                # HTTP 401 is invalid credentials, HTTP 429 is expected rate limiting under high concurrency
                response.success()
            else:
                response.failure(
                    f"Unexpected response code on invalid login: {response.status_code}"
                )
