"""FastAPI endpoints for background task submission, status monitoring, and result retrieval.

Fully protected by authentication and multi-tenant authorization controls.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.errors import AuthorizationException, EntityNotFoundException
from app.core.security import SecurityContext
from app.core.tasks.system import system_ping
from app.modules.auth.dependencies import require_authenticated_user
from app.services.task_service import TaskService, task_service

logger = logging.getLogger("app.api.v1.tasks")

router = APIRouter(prefix="/tasks", tags=["Background Tasks"])


class SystemPingRequest(BaseModel):
    """Optional payload for system ping task submission."""

    message: str = Field(default="ping", description="Message content for worker verification")


class TaskSubmissionResponse(BaseModel):
    """Response returned upon background task submission."""

    task_id: str = Field(description="Unique Celery task identifier")
    status: str = Field(description="Initial task status (e.g. PENDING)")
    queue: str = Field(description="Destination queue name")
    duplicate: bool = Field(
        default=False, description="True if submission was suppressed as duplicate"
    )


class TaskStatusResponse(BaseModel):
    """Current state and execution metadata for a background task."""

    task_id: str = Field(description="Unique Celery task identifier")
    status: str = Field(
        description="Celery task status (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)"
    )
    ready: bool = Field(description="Whether execution has completed")
    successful: bool | None = Field(default=None, description="True if succeeded, False if failed")
    error: str | None = Field(default=None, description="Sanitized error message if failed")


class TaskResultResponse(BaseModel):
    """Final result or failure payload for a completed background task."""

    task_id: str = Field(description="Unique Celery task identifier")
    status: str = Field(description="Task status")
    ready: bool = Field(description="Whether task is complete")
    result: Any | None = Field(default=None, description="Task execution output if successful")
    error: str | None = Field(default=None, description="Error message if task failed")


def get_task_service() -> TaskService:
    """Dependency provider for TaskService."""
    return task_service


async def _verify_task_access(
    task_id: str,
    security_context: SecurityContext,
    service: TaskService,
    redis_client: Any,
) -> None:
    """Verify that the requesting security context is authorized to access the given task."""
    meta = await service.get_task_metadata(task_id, redis_client)
    if meta is not None:
        task_tenant = meta.get("tenant_id")
        if task_tenant:
            # Multi-tenant task: Enforce strict tenant boundary
            if not security_context.is_super_admin:
                if not security_context.tenant_id or str(security_context.tenant_id) != str(
                    task_tenant
                ):
                    raise AuthorizationException(
                        "Not authorized to access tasks from another organization",
                        error_code="TENANT_MISMATCH",
                    )
        else:
            # Non-tenant task: User must be super_admin or creator
            creator_id = meta.get("user_id")
            if not security_context.is_super_admin and str(security_context.user_id) != str(
                creator_id
            ):
                raise AuthorizationException(
                    "Not authorized to access this background task",
                    error_code="FORBIDDEN",
                )
    else:
        # No ownership record found
        if not security_context.is_super_admin:
            raise EntityNotFoundException("Task", task_id)


@router.post(
    "/system/ping",
    response_model=TaskSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit System Ping Background Task",
    description="Enqueue a diagnostic system ping task onto the default queue to verify worker and broker health.",
)
async def submit_system_ping(
    request: Request,
    payload: SystemPingRequest | None = None,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    security_context: SecurityContext = Depends(require_authenticated_user),
    service: TaskService = Depends(get_task_service),
) -> TaskSubmissionResponse:
    """Submit system ping task for asynchronous background processing with auth context."""
    msg = payload.message if payload else "ping"
    redis_client = getattr(request.app.state, "redis_client", None)

    sub_result = await service.submit_task(
        task=system_ping,
        args=(msg,),
        queue="default",
        idempotency_key=idempotency_key,
        tenant_id=security_context.tenant_id,
        user_id=security_context.user_id,
        redis_client=redis_client,
    )

    return TaskSubmissionResponse(
        task_id=sub_result.task_id,
        status=sub_result.status,
        queue=sub_result.queue,
        duplicate=sub_result.duplicate,
    )


@router.get(
    "/{task_id}/status",
    response_model=TaskStatusResponse,
    summary="Query Task Execution Status",
    description="Poll current execution state, retry count, or completion status of a Celery background task.",
)
async def get_task_status_endpoint(
    task_id: str,
    request: Request,
    security_context: SecurityContext = Depends(require_authenticated_user),
    service: TaskService = Depends(get_task_service),
) -> TaskStatusResponse:
    """Retrieve execution status for the specified task ID with tenant authorization check."""
    if not task_id or len(task_id.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id cannot be empty",
        )

    redis_client = getattr(request.app.state, "redis_client", None)
    await _verify_task_access(task_id, security_context, service, redis_client)

    status_result = await service.get_task_status(task_id)
    return TaskStatusResponse(
        task_id=status_result.task_id,
        status=status_result.status,
        ready=status_result.ready,
        successful=status_result.successful,
        error=status_result.error,
    )


@router.get(
    "/{task_id}/result",
    response_model=TaskResultResponse,
    summary="Retrieve Task Result",
    description="Fetch the return value or failure information of a completed background task.",
)
async def get_task_result_endpoint(
    task_id: str,
    request: Request,
    security_context: SecurityContext = Depends(require_authenticated_user),
    service: TaskService = Depends(get_task_service),
) -> TaskResultResponse:
    """Retrieve task execution output or error details with tenant authorization check."""
    if not task_id or len(task_id.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id cannot be empty",
        )

    redis_client = getattr(request.app.state, "redis_client", None)
    await _verify_task_access(task_id, security_context, service, redis_client)

    status_result = await service.get_task_status(task_id)

    return TaskResultResponse(
        task_id=status_result.task_id,
        status=status_result.status,
        ready=status_result.ready,
        result=status_result.result,
        error=status_result.error,
    )
