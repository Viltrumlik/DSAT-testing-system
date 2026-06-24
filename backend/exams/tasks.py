from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

from .engine_db_guard import TransitionConflict
from .models import TestAttempt
from .metrics import incr as metric_incr

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def compact_module_question_orders(self, module_id: int) -> dict:
    """
    Dense reindex 0..n-1 for a module (off request path). Safe to run concurrently; work is idempotent.
    """
    from .question_ordering import dense_compact_module_orders_locked

    updated = dense_compact_module_orders_locked(module_id)
    metric_incr("exam_question_order_compact_task_total")
    logger.info("question_order_compact_task module_id=%s rows_updated=%s", module_id, updated)
    return {"module_id": module_id, "rows_updated": updated}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def score_attempt_async(self, attempt_id: int, trace_id: str | None = None) -> dict:
    """
    Idempotent scoring task.
    Preconditions:
      - attempt.current_state == SCORING
    Postconditions:
      - attempt transitions to COMPLETED and score is persisted
    """
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().select_related("practice_test").get(pk=attempt_id)
        if attempt.current_state == TestAttempt.STATE_COMPLETED and attempt.is_completed:
            return {"status": "noop", "reason": "already_completed", "attempt_id": attempt_id}
        if attempt.current_state != TestAttempt.STATE_SCORING:
            return {
                "status": "noop",
                "reason": f"state_is_{attempt.current_state}",
                "attempt_id": attempt_id,
            }

        # Compute score and finalize (DB guarded: concurrent workers reconcile below).
        try:
            attempt.complete_test()
        except TransitionConflict:
            attempt.refresh_from_db()
            if not (attempt.is_completed and attempt.current_state == TestAttempt.STATE_COMPLETED):
                raise

    attempt = TestAttempt.objects.get(pk=attempt_id)
    metric_incr("scoring_completed")
    if trace_id:
        logger.info("attempt_scored attempt_id=%s score=%s trace_id=%s", attempt_id, attempt.score, trace_id)
    else:
        logger.info("attempt_scored attempt_id=%s score=%s", attempt_id, attempt.score)
    return {"status": "ok", "attempt_id": attempt_id, "score": attempt.score}

