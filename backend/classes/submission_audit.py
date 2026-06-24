"""
Append-only audit trail for submissions and reviews.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model

from .models import SubmissionAuditEvent

User = get_user_model()
logger = logging.getLogger("classes.submission_audit")

AUDIT_SCHEMA_VERSION = 1


def audit_submission_event(
    submission_id: int,
    actor_id: int | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    submission_revision: int | None = None,
) -> SubmissionAuditEvent:
    """
    Enforced audit entry: merges schema version and optional submission revision into payload.
    Use this for all classroom submission lifecycle events (not raw ``log_submission_event``).
    """
    pl: dict[str, Any] = dict(payload or {})
    pl["audit_schema_version"] = AUDIT_SCHEMA_VERSION
    if submission_revision is not None:
        pl["submission_revision"] = submission_revision
    return log_submission_event(submission_id, actor_id, event_type, pl)


def log_submission_event(
    submission_id: int,
    actor_id: int | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> SubmissionAuditEvent:
    """
    Persist an audit row. Never raises for logging failures in production paths
    (logs error and re-raises only if DB is broken).
    """
    try:
        return SubmissionAuditEvent.objects.create(
            submission_id=submission_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload or {},
        )
    except Exception:
        logger.exception(
            "submission_audit_write_failed submission_id=%s event_type=%s",
            submission_id,
            event_type,
        )
        raise
