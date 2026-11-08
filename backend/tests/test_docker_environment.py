"""Comprehensive verification tests for Step 3.6 Docker development and production environment.

Validates:
1. Docker Compose base (production) and development override specifications.
2. 5-service orchestration: postgres, redis, backend, celery_worker, frontend.
3. Private internal network, volume persistence, and localhost port isolation.
4. Multi-stage Dockerfiles, non-root users, health checks, and .dockerignore rules.
5. Celery health probe and queue inspection.
6. Environment variable definitions and secret separation.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from app.core.celery_app import CELERY_QUEUES, celery_app
from app.core.celery_health import (
    EXPECTED_TASK_QUEUES,
    check_celery_broker_health,
    check_celery_queues_health,
    check_celery_workers_health,
    run_health_probe,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROD_COMPOSE_PATH = REPO_ROOT / "infrastructure" / "docker" / "docker-compose.yml"
DEV_COMPOSE_PATH = REPO_ROOT / "infrastructure" / "docker" / "docker-compose.dev.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
BACKEND_DOCKERIGNORE = REPO_ROOT / "backend" / ".dockerignore"
FRONTEND_DOCKERIGNORE = REPO_ROOT / "frontend" / ".dockerignore"
BACKEND_ENTRYPOINT = REPO_ROOT / "backend" / "entrypoint.sh"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_DEV_EXAMPLE = REPO_ROOT / ".env.dev.example"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ==============================================================================
# 1. Docker Compose Base Architecture Tests
# ==============================================================================


def test_docker_compose_services_presence() -> None:
    """Verify all 5 required services are present in the base Compose file."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    services = compose.get("services", {})
    expected = {"postgres", "redis", "backend", "celery_worker", "frontend"}
    assert expected.issubset(
        set(services.keys())
    ), f"Missing services: {expected - set(services.keys())}"


def test_docker_compose_private_network() -> None:
    """Verify a dedicated private bridge network is defined and utilized by all services."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    networks = compose.get("networks", {})
    assert "ai_hr_network" in networks
    assert networks["ai_hr_network"]["driver"] == "bridge"

    for name, svc in compose["services"].items():
        svc_nets = svc.get("networks", [])
        assert "ai_hr_network" in svc_nets, f"Service '{name}' is not attached to 'ai_hr_network'"


def test_docker_compose_persistent_volumes() -> None:
    """Verify named persistent volumes exist for PostgreSQL and Redis."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    volumes = compose.get("volumes", {})
    assert "postgres_data" in volumes
    assert "redis_data" in volumes

    # Verify services mount the named volumes
    pg_vols = compose["services"]["postgres"]["volumes"]
    assert any("postgres_data:/var/lib/postgresql/data" in v for v in pg_vols)

    redis_vols = compose["services"]["redis"]["volumes"]
    assert any("redis_data:/data" in v for v in redis_vols)


def test_docker_compose_no_unnecessary_port_exposure_in_production() -> None:
    """Verify database, Redis, and Celery worker never publish host ports in base/production compose."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    services = compose["services"]

    assert "ports" not in services["postgres"], "postgres must not publish host ports in production"
    assert "ports" not in services["redis"], "redis must not publish host ports in production"
    assert "ports" not in services["celery_worker"], "celery_worker must not publish host ports"


def test_docker_compose_healthchecks_all_services() -> None:
    """Verify sensible health checks are defined for all 5 services."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    for name, svc in compose["services"].items():
        hc = svc.get("healthcheck")
        assert hc is not None, f"Service '{name}' is missing a healthcheck"
        assert "test" in hc, f"Service '{name}' healthcheck has no test command"
        assert "interval" in hc
        assert "timeout" in hc
        assert "retries" in hc


def test_docker_compose_startup_dependencies_and_ordering() -> None:
    """Verify health-based service dependencies ensure correct startup ordering."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    services = compose["services"]

    # Backend depends on healthy postgres and redis
    b_deps = services["backend"]["depends_on"]
    assert b_deps["postgres"]["condition"] == "service_healthy"
    assert b_deps["redis"]["condition"] == "service_healthy"

    # Celery worker depends on healthy postgres and redis
    cw_deps = services["celery_worker"]["depends_on"]
    assert cw_deps["postgres"]["condition"] == "service_healthy"
    assert cw_deps["redis"]["condition"] == "service_healthy"

    # Frontend depends on healthy backend
    f_deps = services["frontend"]["depends_on"]
    assert f_deps["backend"]["condition"] == "service_healthy"


def test_docker_compose_graceful_shutdown() -> None:
    """Verify all services configure appropriate restart and graceful stop policies."""
    compose = _load_yaml(PROD_COMPOSE_PATH)
    for name, svc in compose["services"].items():
        assert svc.get("restart") == "unless-stopped", f"Service '{name}' missing restart policy"
        assert svc.get("stop_signal") == "SIGTERM", f"Service '{name}' missing SIGTERM stop signal"
        assert "stop_grace_period" in svc, f"Service '{name}' missing stop_grace_period"


# ==============================================================================
# 2. Docker Compose Development Override Tests
# ==============================================================================


def test_dev_compose_loopback_only_port_publishing() -> None:
    """Verify dev compose publishes postgres and redis exclusively to 127.0.0.1 (never 0.0.0.0)."""
    dev_compose = _load_yaml(DEV_COMPOSE_PATH)
    services = dev_compose.get("services", {})

    pg_ports = services["postgres"]["ports"]
    for p in pg_ports:
        assert p.startswith(
            "127.0.0.1:"
        ), f"PostgreSQL port '{p}' must be bound exclusively to 127.0.0.1"

    redis_ports = services["redis"]["ports"]
    for p in redis_ports:
        assert p.startswith(
            "127.0.0.1:"
        ), f"Redis port '{p}' must be bound exclusively to 127.0.0.1"


def test_dev_compose_source_mounting_and_reload() -> None:
    """Verify dev compose mounts source directories and configures hot reload."""
    dev_compose = _load_yaml(DEV_COMPOSE_PATH)
    services = dev_compose.get("services", {})

    # Backend source mount and reload
    b_vols = services["backend"]["volumes"]
    assert any("../../backend:/app" in v for v in b_vols)
    assert "--reload" in services["backend"]["command"]

    # Frontend source mount, dev target, and isolated node_modules
    f_svc = services["frontend"]
    assert f_svc.get("build", {}).get("target") == "dev"
    f_vols = f_svc["volumes"]
    assert any("../../frontend:/app" in v for v in f_vols)
    assert "/app/node_modules" in f_vols
    assert "/app/.next" in f_vols


# ==============================================================================
# 3. Dockerfile & Image Configuration Tests
# ==============================================================================


def test_backend_dockerfile_multi_stage_and_security() -> None:
    """Verify backend Dockerfile uses multi-stage build, pinned base, and non-root user."""
    content = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM python:3.11-slim AS builder" in content
    assert "FROM python:3.11-slim AS runner" in content
    assert "useradd -u 10001 -g appgroup -s /bin/bash -m appuser" in content
    assert "USER appuser" in content
    assert "ENTRYPOINT" in content
    assert "/app/entrypoint.sh" in content
    assert "HEALTHCHECK" in content


def test_frontend_dockerfile_multi_stage_and_security() -> None:
    """Verify frontend Dockerfile uses multi-stage build, dev target, and non-root user."""
    content = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM node:20-alpine AS base" in content
    assert "FROM base AS deps" in content
    assert "FROM base AS dev" in content
    assert "FROM base AS builder" in content
    assert "FROM node:20-alpine AS runner" in content
    assert "adduser --system --uid 1001 nextjs" in content
    assert "USER nextjs" in content
    assert "HEALTHCHECK" in content


def test_dockerignore_files_completeness() -> None:
    """Verify .dockerignore files exclude virtualenvs, secrets, cache, and build outputs."""
    b_ignore = BACKEND_DOCKERIGNORE.read_text(encoding="utf-8")
    assert ".venv/" in b_ignore
    assert "__pycache__/" in b_ignore
    assert ".git/" in b_ignore
    assert ".env" in b_ignore

    f_ignore = FRONTEND_DOCKERIGNORE.read_text(encoding="utf-8")
    assert "node_modules/" in f_ignore
    assert ".next/" in f_ignore
    assert ".git/" in f_ignore
    assert ".env" in f_ignore


def test_backend_entrypoint_script_safety() -> None:
    """Verify entrypoint script runs migrations on uvicorn startup and fails fast on errors."""
    content = BACKEND_ENTRYPOINT.read_text(encoding="utf-8")
    assert "set -eo pipefail" in content
    assert "alembic upgrade head" in content
    assert 'if [ "${RUN_MIGRATIONS:-true}" = "true" ] && [ "$1" = "uvicorn" ];' in content
    assert 'exec "$@"' in content


# ==============================================================================
# 4. Celery Health Probe & Queue Tests
# ==============================================================================


def test_celery_queues_completeness() -> None:
    """Verify all 7 expected queues are configured."""
    actual_queues = {q.name for q in CELERY_QUEUES}
    assert actual_queues == EXPECTED_TASK_QUEUES


def test_celery_health_probe_broker_and_workers() -> None:
    """Verify health probe checks broker and responds to --workers and --queues flags."""
    mock_conn = MagicMock()
    mock_conn.ensure_connection.return_value = True
    mock_conn.default_channel.client.ping.return_value = True

    with patch.object(celery_app, "connection_for_read", return_value=mock_conn):
        mock_conn.__enter__.return_value = mock_conn

        # 1. Basic broker probe
        assert check_celery_broker_health() is True
        assert run_health_probe() is True

        # 2. Worker inspect ping probe
        with patch.object(celery_app.control, "inspect") as mock_inspect:
            inspector = MagicMock()
            mock_inspect.return_value = inspector
            inspector.ping.return_value = {"celery@worker1": {"ok": "pong"}}
            inspector.active_queues.return_value = {
                "celery@worker1": [{"name": q} for q in EXPECTED_TASK_QUEUES]
            }

            assert check_celery_workers_health() is True
            assert check_celery_queues_health() is True

            # Test run_health_probe with workers enabled via env var
            with patch.dict(os.environ, {"CELERY_HEALTH_CHECK_WORKERS": "true"}):
                assert run_health_probe() is True

            # Test missing queues fails
            inspector.active_queues.return_value = {"celery@worker1": [{"name": "default"}]}
            assert check_celery_queues_health() is False


# ==============================================================================
# 5. Environment & Secret Configuration Tests
# ==============================================================================


def test_env_templates_internal_hostnames_and_secret_separation() -> None:
    """Verify .env templates use internal container hostnames and keep secrets separate."""
    dev_content = ENV_DEV_EXAMPLE.read_text(encoding="utf-8")
    prod_content = ENV_EXAMPLE.read_text(encoding="utf-8")

    # Internal container hostnames (never localhost for container-to-container)
    assert "@postgres:5432/ai_hr_db" in dev_content
    assert "@redis:6379/" in dev_content
    assert "INTERNAL_API_URL=http://backend:8000/api/v1" in dev_content

    # In production template, all passwords must be empty placeholders
    assert "POSTGRES_PASSWORD=\n" in prod_content
    assert "REDIS_PASSWORD=\n" in prod_content
    assert "JWT_SECRET_KEY=\n" in prod_content
