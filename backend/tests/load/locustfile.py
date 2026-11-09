"""Locust performance and load testing suite for the AI HR Intelligence Platform.

Simulates concurrent user load against API endpoints:
1. Liveness and readiness probe polling under sustained throughput.
2. Background task enqueuing and status query polling.
3. Authentication and validation response metrics.
"""

from __future__ import annotations

from locust import HttpUser, between, task


class PlatformLoadTestUser(HttpUser):
    """Simulates platform traffic under concurrent multi-user load."""

    wait_time = between(0.05, 0.2)

    @task(5)
    def liveness_check(self) -> None:
        """Sustained liveness verification under concurrency."""
        self.client.get("/api/v1/health", name="/api/v1/health")

    @task(3)
    def readiness_check(self) -> None:
        """Downstream dependency (PostgreSQL, Redis) readiness under concurrency."""
        self.client.get("/api/v1/health/ready", name="/api/v1/health/ready")

    @task(2)
    def submit_diagnostic_task(self) -> None:
        """Simulate task queue submission and status check."""
        res = self.client.post(
            "/api/v1/tasks/system/ping",
            json={"message": "load-test-ping"},
            headers={"Content-Type": "application/json"},
            name="/api/v1/tasks/system/ping",
        )
        if res.status_code == 202:
            task_data = res.json()
            task_id = task_data.get("task_id")
            if task_id:
                self.client.get(
                    f"/api/v1/tasks/{task_id}/status",
                    name="/api/v1/tasks/[task_id]/status",
                )
