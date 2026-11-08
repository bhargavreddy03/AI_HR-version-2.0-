"""Centralized security event auditing, structured log emission, and log injection defense.

Conforms to Architecture Document 07 Section 2, 16 Section 1, and DATABASE_SECURITY_INVENTORY.md.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.middleware import get_correlation_id

logger = logging.getLogger("security.audit")

# Sensitive keys that must be redacted from audit details
SENSITIVE_AUDIT_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "refresh_token_hash",
        "mfa_secret",
        "secret",
        "code",
        "backup_codes",
        "pepper",
        "key",
        "credential",
        "authorization",
        "cookie",
    }
)


class SecurityAuditEvent(BaseModel):
    """Structured security audit event descriptor."""

    event_type: str = Field(..., description="Canonical security event identifier")
    outcome: str = Field(..., description="'SUCCESS' or 'FAILURE'")
    actor_id: str | None = Field(default=None, description="UUID of actor initiating action")
    tenant_id: str | None = Field(default=None, description="UUID of active tenant")
    client_ip: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client User-Agent header")
    correlation_id: str = Field(
        default_factory=get_correlation_id, description="Request correlation ID"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="UTC ISO-8601 timestamp",
    )
    details: dict[str, Any] = Field(default_factory=dict, description="Sanitized event metadata")


def sanitize_audit_value(val: Any) -> Any:
    """Escape control characters and newlines to prevent log injection."""
    if isinstance(val, str):
        # Escape newlines, carriage returns, and control characters
        return val.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if isinstance(val, dict):
        return {
            str(k): "******"
            if any(sens in str(k).lower() for sens in SENSITIVE_AUDIT_KEYS)
            else sanitize_audit_value(v)
            for k, v in val.items()
        }
    if isinstance(val, list | tuple):
        return [sanitize_audit_value(elem) for elem in val]
    return val


def sanitize_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub credentials and escape control characters from audit metadata."""
    sanitized: dict[str, Any] = {}
    for key, val in details.items():
        if any(sens in str(key).lower() for sens in SENSITIVE_AUDIT_KEYS):
            sanitized[str(key)] = "******"
        else:
            sanitized[str(key)] = sanitize_audit_value(val)
    return sanitized


def log_security_event(
    event_type: str,
    outcome: str,
    actor_id: UUID | str | None = None,
    tenant_id: UUID | str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    """Emit a structured security audit event log with log-injection protection and secret redaction."""
    safe_details = sanitize_audit_details(details or {})
    event = SecurityAuditEvent(
        event_type=event_type,
        outcome=outcome.upper(),
        actor_id=str(actor_id) if actor_id else None,
        tenant_id=str(tenant_id) if tenant_id else None,
        client_ip=sanitize_audit_value(client_ip) if client_ip else None,
        user_agent=sanitize_audit_value(user_agent)[:256] if user_agent else None,
        correlation_id=get_correlation_id(),
        details=safe_details,
    )

    # Emit JSON structured log line
    serialized = json.dumps(event.model_dump())
    if event.outcome == "FAILURE":
        logger.warning("SECURITY_AUDIT: %s", serialized)
    else:
        logger.info("SECURITY_AUDIT: %s", serialized)

    return event
