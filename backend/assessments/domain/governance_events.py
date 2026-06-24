"""
Governance event dispatch service.

DESIGN:
  All significant state transitions in the immutable academic-record platform
  MUST emit a GovernanceEvent. This creates an append-only audit timeline
  that operators can query per-entity, per-actor, and per-event-type.

TRANSACTION SEMANTICS:
  Events are emitted inside the caller's DB transaction (synchronous).
  If the outer transaction rolls back, the event row rolls back with it.
  This ensures event/state consistency: an event exists IFF the action
  it describes was committed.

ERROR HANDLING:
  emit_governance_event() wraps the DB write in try/except. A governance
  event emission failure is logged but NEVER propagates to the caller.
  The primary business action (publish, grading, assignment) must not
  fail because of audit-log issues.

CORRELATION IDs:
  Pass correlation_id from the HTTP request (e.g. X-Request-ID header or
  a UUID generated per request) to link events that belong to the same
  user action across DB tables and log lines.

ENTITY TYPES:
  Use the Django model class name as entity_type for consistency:
  - "AssessmentSet"
  - "AssessmentSetVersion"
  - "HomeworkAssignment"
  - "AssessmentAttempt"
  - "AssessmentAnswer"

USAGE:
    from assessments.domain.governance_events import emit_governance_event
    from assessments.models import GovernanceEvent

    emit_governance_event(
        event_type=GovernanceEvent.EVENT_PUBLISH,
        actor=request.user,
        entity_type="AssessmentSetVersion",
        entity_id=version.pk,
        payload={
            "set_id": aset.pk,
            "version_number": version.version_number,
            "question_count": version.question_count,
            "checksum": version.snapshot_checksum[:16],
        },
        correlation_id=request.META.get("HTTP_X_REQUEST_ID", ""),
    )
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def emit_governance_event(
    *,
    event_type: str,
    actor,                  # AUTH_USER_MODEL instance or None (system/async)
    entity_type: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
    correlation_id: str = "",
) -> None:
    """
    Emit a GovernanceEvent record inside the current DB transaction.

    Errors are logged at ERROR level but do NOT propagate — governance event
    failure must never block the primary business action.

    Args:
        event_type:     One of GovernanceEvent.EVENT_* constants.
        actor:          Authenticated user performing the action, or None
                        for system/Celery actions.
        entity_type:    Django model class name (e.g. "AssessmentSetVersion").
        entity_id:      Primary key of the entity being acted upon.
        payload:        Arbitrary structured data for operator debugging.
        correlation_id: Request trace ID linking related events.
    """
    from assessments.models import GovernanceEvent  # late import: avoid circular

    try:
        actor_instance = None
        actor_email = ""
        if actor is not None:
            if getattr(actor, "is_authenticated", False):
                actor_instance = actor
                actor_email = getattr(actor, "email", "") or ""

        GovernanceEvent.objects.create(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor_instance,
            actor_email=actor_email,
            payload=payload or {},
            correlation_id=correlation_id or "",
            occurred_at=timezone.now(),
        )
    except Exception as exc:
        logger.error(
            "governance_events.emit_failed: event_type=%s entity=%s#%s correlation=%s error=%r",
            event_type,
            entity_type,
            entity_id,
            correlation_id,
            exc,
            exc_info=True,
        )


def emit_fallback_path_used(
    *,
    attempt_id: int,
    set_id: int,
    context: str,  # "grading" | "bundle" | "submit"
    actor=None,
    correlation_id: str = "",
) -> None:
    """
    Convenience wrapper for FALLBACK_PATH_USED events.

    Called whenever the live-lookup fallback path is used instead of the
    immutable snapshot. This event is the primary telemetry signal for
    measuring fallback sunset progress.

    OPERATORS: monitor event_type=fallback_path_used in governance_events.
    When count drops to 0, the fallback code paths can be removed.
    """
    from assessments.models import GovernanceEvent

    emit_governance_event(
        event_type=GovernanceEvent.EVENT_FALLBACK_PATH_USED,
        actor=actor,
        entity_type="AssessmentAttempt",
        entity_id=attempt_id,
        payload={
            "set_id": set_id,
            "context": context,  # where the fallback was triggered
            "reason": "set_version_null",  # always null for now
        },
        correlation_id=correlation_id,
    )
