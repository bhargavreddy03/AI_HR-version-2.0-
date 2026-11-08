"""Asynchronous background tasks for document processing pipeline."""

from __future__ import annotations

import logging
from typing import Any

from app.core.celery_app import celery_app
from app.core.tasks.base import BaseTask, TransientTaskError

logger = logging.getLogger("app.modules.documents.tasks")


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.modules.documents.tasks.parse_document",
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def parse_document(
    self: Any,
    document_id: str,
    tenant_id: str,
    s3_key: str | None = None,
) -> dict[str, Any]:
    """Sample document parsing background task routed to document_processing queue."""
    logger.info(
        "Parsing document: id=%s, tenant_id=%s, s3_key=%s",
        document_id,
        tenant_id,
        s3_key,
    )
    return {
        "status": "completed",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "queue": getattr(self.request, "delivery_info", {}).get(
            "routing_key", "document_processing"
        ),
        "task_id": self.request.id,
    }
