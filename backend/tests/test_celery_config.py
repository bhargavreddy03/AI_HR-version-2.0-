"""Unit tests for Celery application configuration, queue routing, and task registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.celery_app import (
    CELERY_QUEUES,
    CELERY_TASK_ROUTES,
    celery_app,
    create_celery_app,
    get_celery_config,
)
from app.core.celery_health import check_celery_broker_health, run_health_probe
from app.core.config import Settings


def test_celery_application_configuration() -> None:
    """Verify production Celery settings adhere to security, reliability, and serialization rules."""
    conf = celery_app.conf

    # Task and Result Serialization must strictly be JSON
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert conf.accept_content == ["json"]
    assert conf.result_accept_content == ["json"]

    # Timezone and UTC
    assert conf.timezone == "UTC"
    assert conf.enable_utc is True

    # Reliability and worker dispatch
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.broker_connection_retry_on_startup is True

    # Tracking
    assert conf.task_track_started is True
    assert conf.worker_send_task_events is True


def test_celery_queues_and_routing() -> None:
    """Verify all 7 approved queues and routing maps exist and are configured."""
    queue_names = {q.name for q in CELERY_QUEUES}
    expected_queues = {
        "default",
        "document_processing",
        "resume_parsing",
        "embedding_generation",
        "candidate_matching",
        "notifications",
        "reporting",
    }
    assert queue_names == expected_queues, f"Mismatch in configured queues: {queue_names}"

    # Verify task routing map
    assert CELERY_TASK_ROUTES["app.core.tasks.system.*"]["queue"] == "default"
    assert CELERY_TASK_ROUTES["app.modules.documents.tasks.*"]["queue"] == "document_processing"
    assert CELERY_TASK_ROUTES["app.modules.candidates.tasks.*"]["queue"] == "resume_parsing"
    assert CELERY_TASK_ROUTES["app.modules.embeddings.tasks.*"]["queue"] == "embedding_generation"
    assert CELERY_TASK_ROUTES["app.modules.screening.tasks.*"]["queue"] == "candidate_matching"
    assert CELERY_TASK_ROUTES["app.modules.notifications.tasks.*"]["queue"] == "notifications"
    assert CELERY_TASK_ROUTES["app.modules.reporting.tasks.*"]["queue"] == "reporting"


def test_celery_task_registration_and_autodiscovery() -> None:
    """Verify sample and foundational tasks are discovered and registered with Celery."""
    registered_tasks = set(celery_app.tasks.keys())

    assert "app.core.tasks.system.system_ping" in registered_tasks
    assert "app.core.tasks.system.sample_transient_retry" in registered_tasks
    assert "app.core.tasks.system.sample_permanent_failure" in registered_tasks
    assert "app.core.tasks.system.sample_idempotent_task" in registered_tasks
    assert "app.modules.documents.tasks.parse_document" in registered_tasks


def test_celery_time_limits_and_concurrency() -> None:
    """Verify task time limits and concurrency settings inherit from Settings."""
    settings = Settings(
        CELERY_WORKER_CONCURRENCY=4,
        CELERY_TASK_TIME_LIMIT=600,
        CELERY_TASK_SOFT_TIME_LIMIT=540,
        CELERY_RESULT_EXPIRES=172800,
    )
    config = get_celery_config(settings)

    assert config["worker_concurrency"] == 4
    assert config["task_time_limit"] == 600
    assert config["task_soft_time_limit"] == 540
    assert config["result_expires"] == 172800


def test_celery_custom_instance_creation() -> None:
    """Verify create_celery_app creates an independent configured Celery instance."""
    custom_app = create_celery_app()
    assert custom_app.main == "ai_hr"
    assert custom_app.conf.task_serializer == "json"


def test_celery_health_probe_broker_check() -> None:
    """Verify check_celery_broker_health probe succeeds when connection is valid and catches failures."""
    mock_conn = MagicMock()
    mock_conn.ensure_connection.return_value = True
    mock_conn.default_channel.client.ping.return_value = True

    with patch.object(celery_app, "connection_for_read", return_value=mock_conn):
        mock_conn.__enter__.return_value = mock_conn
        assert check_celery_broker_health() is True
        assert run_health_probe() is True

    # Verify probe returns False on exception
    with patch.object(
        celery_app, "connection_for_read", side_effect=Exception("Redis unreachable")
    ):
        assert check_celery_broker_health() is False
        assert run_health_probe() is False


def test_docker_compose_celery_worker_configuration() -> None:
    """Verify docker-compose.yml defines celery_worker with no exposed ports, dependencies, and healthcheck."""
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parent.parent.parent
    prod_compose = repo_root / "infrastructure" / "docker" / "docker-compose.yml"
    dev_compose = repo_root / "infrastructure" / "docker" / "docker-compose.dev.yml"

    with open(prod_compose, encoding="utf-8") as f:
        prod_data = yaml.safe_load(f)

    assert "celery_worker" in prod_data["services"]
    cw_prod = prod_data["services"]["celery_worker"]
    assert "ports" not in cw_prod, "celery_worker must not publish ports"
    assert cw_prod["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert cw_prod["depends_on"]["redis"]["condition"] == "service_healthy"
    assert cw_prod["stop_signal"] == "SIGTERM"
    assert "celery_health" in "".join(cw_prod["healthcheck"]["test"])

    with open(dev_compose, encoding="utf-8") as f:
        dev_data = yaml.safe_load(f)

    assert "celery_worker" in dev_data["services"]
