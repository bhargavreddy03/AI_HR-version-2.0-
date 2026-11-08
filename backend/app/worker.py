"""Celery worker execution entry point for Docker containers and local development."""

from __future__ import annotations

import sys

from app.core.celery_app import celery_app
from app.core.config import get_settings

__all__ = ["celery_app"]

if __name__ == "__main__":
    settings = get_settings()
    worker_args = [
        "worker",
        f"--loglevel={settings.LOG_LEVEL}",
        "-Q",
        "default,document_processing,resume_parsing,embedding_generation,candidate_matching,notifications,reporting",
        f"--concurrency={settings.CELERY_WORKER_CONCURRENCY}",
    ]
    celery_app.start(argv=[sys.argv[0]] + worker_args)
