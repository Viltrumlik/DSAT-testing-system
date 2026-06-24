"""Question Bank audit trail.

Reuses the immutable, append-only ``assessments.GovernanceEvent`` store (no new
model, no migration — ``event_type`` choices are not DB-enforced). Events are
written INSIDE the action's atomic transaction so the audit row commits iff the
action does. Emission never blocks the business action (emit swallows + logs).
"""
from __future__ import annotations

from assessments.domain.governance_events import emit_governance_event

# Event taxonomy (namespaced under qb_*) ----------------------------------------
EVT_CLASSIFY = "qb_question_classify"
EVT_ACCEPT_SUGGESTION = "qb_question_accept_suggestion"
EVT_APPROVE = "qb_question_approve"
EVT_REJECT = "qb_question_reject"
EVT_CREATE = "qb_question_create"
EVT_UPDATE = "qb_question_update"
EVT_ARCHIVE = "qb_question_archive"
EVT_RESTORE = "qb_question_restore"
EVT_BATCH_PROMOTE = "qb_batch_promote"

ENTITY_QUESTION = "BankQuestion"
ENTITY_BATCH = "ImportBatch"


def record_question_event(
    *, event_type: str, question, actor, previous_state: str, new_state: str, extra: dict | None = None,
) -> None:
    payload: dict = {
        "qb_id": question.qb_id,
        "previous_state": previous_state,
        "new_state": new_state,
    }
    if extra:
        payload.update(extra)
    emit_governance_event(
        event_type=event_type,
        actor=actor,
        entity_type=ENTITY_QUESTION,
        entity_id=question.id,
        payload=payload,
    )


def record_batch_event(*, batch, actor, promoted_count: int, extra: dict | None = None) -> None:
    payload: dict = {"promoted_count": promoted_count, "batch_status": batch.status}
    if extra:
        payload.update(extra)
    emit_governance_event(
        event_type=EVT_BATCH_PROMOTE,
        actor=actor,
        entity_type=ENTITY_BATCH,
        entity_id=batch.id,
        payload=payload,
    )
