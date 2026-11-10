"""Centralized Celery application configuration, queue routing, and task lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from celery import Celery
from kombu.entity import Queue

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Approved direct queues for platform background workloads
CELERY_QUEUES: tuple[Queue, ...] = (
    Queue("default", routing_key="default"),
    Queue("document_processing", routing_key="document_processing"),
    Queue("resume_parsing", routing_key="resume_parsing"),
    Queue("embedding_generation", routing_key="embedding_generation"),
    Queue("candidate_matching", routing_key="candidate_matching"),
    Queue("notifications", routing_key="notifications"),
    Queue("reporting", routing_key="reporting"),
)

# Deterministic task-to-queue routing map
CELERY_TASK_ROUTES: dict[str, dict[str, str]] = {
    "app.core.tasks.system.*": {"queue": "default", "routing_key": "default"},
    "app.modules.documents.tasks.*": {
        "queue": "document_processing",
        "routing_key": "document_processing",
    },
    "app.modules.candidates.tasks.*": {
        "queue": "resume_parsing",
        "routing_key": "resume_parsing",
    },
    "app.modules.embeddings.tasks.*": {
        "queue": "embedding_generation",
        "routing_key": "embedding_generation",
    },
    "app.modules.screening.tasks.*": {
        "queue": "candidate_matching",
        "routing_key": "candidate_matching",
    },
    "app.modules.notifications.tasks.*": {
        "queue": "notifications",
        "routing_key": "notifications",
    },
    "app.modules.reporting.tasks.*": {
        "queue": "reporting",
        "routing_key": "reporting",
    },
}

# Modules participating in automated task autodiscovery
AUTODISCOVER_MODULES: list[str] = [
    "app.modules.auth",
    "app.modules.documents",
    "app.modules.candidates",
    "app.modules.embeddings",
    "app.modules.screening",
    "app.modules.reporting",
    "app.modules.notifications",
]


def get_celery_config(settings: Settings) -> dict[str, Any]:
    """Build production-grade Celery configuration dictionary from Settings."""
    return {
        "broker_url": settings.CELERY_BROKER_URL,
        "result_backend": settings.CELERY_RESULT_BACKEND,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "result_accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_track_started": True,
        "task_time_limit": settings.CELERY_TASK_TIME_LIMIT,
        "task_soft_time_limit": settings.CELERY_TASK_SOFT_TIME_LIMIT,
        "result_expires": settings.CELERY_RESULT_EXPIRES,
        "task_default_queue": settings.CELERY_TASK_DEFAULT_QUEUE,
        "task_default_exchange": "",
        "task_default_routing_key": "default",
        "task_queues": CELERY_QUEUES,
        "task_routes": CELERY_TASK_ROUTES,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "worker_prefetch_multiplier": 1,
        "worker_concurrency": settings.CELERY_WORKER_CONCURRENCY,
        "broker_connection_retry_on_startup": True,
        "worker_send_task_events": True,
    }


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Instantiate and configure Celery application with modular monolith task autodiscovery."""
    cfg = settings or get_settings()
    app = Celery("ai_hr")
    app.conf.update(get_celery_config(cfg))
    return app


celery_app: Celery = create_celery_app()
# Autodiscover tasks now that celery_app is defined and bound in the module namespace
celery_app.autodiscover_tasks(["app.core.tasks"], related_name="system", force=True)
celery_app.autodiscover_tasks(AUTODISCOVER_MODULES, force=True)
