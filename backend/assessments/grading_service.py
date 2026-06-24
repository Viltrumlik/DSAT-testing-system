from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from .grading import grade_answer
from .models import (
    AssessmentAttempt,
    AssessmentAnswer,
    AssessmentQuestion,
    AssessmentResult,
    AssessmentAttemptAuditEvent,
)


def _questions_from_attempt(att: AssessmentAttempt) -> tuple[list[Any], dict[int, Any]]:
    """
    Resolve the canonical question list for grading, preferring the immutable
    snapshot pinned on the attempt (att.set_version) and falling back to live
    database lookup for pre-snapshot attempts.

    Returns:
        (questions_list, q_by_id_dict)

    SNAPSHOT PATH (att.set_version_id is not None):
      - Reads from att.set_version.snapshot_json — zero live question lookups.
      - Validates schema compatibility before grading.
      - Returns lightweight dicts wrapped in _SnapshotQuestion namedtuple-likes.

    LIVE PATH (att.set_version_id is None):
      - Legacy behaviour: reads active AssessmentQuestion rows from DB.
      - Used for all attempts created before the snapshot architecture.
      - Emits a GovernanceEvent.EVENT_FALLBACK_PATH_USED for sunset monitoring.
    """
    if att.set_version_id is not None:
        # Snapshot path — grade against the frozen content that was delivered.
        from .domain.snapshot_builder import questions_from_snapshot
        from .domain.snapshot_compat import adapt_snapshot, can_grade_snapshot

        snapshot_json = att.set_version.snapshot_json

        # Schema compatibility check — raise early if this code is too old.
        ok, reason = can_grade_snapshot(snapshot_json)
        if not ok:
            raise ValueError(
                f"Cannot grade attempt #{att.pk}: snapshot schema incompatible. "
                f"Reason: {reason}"
            )

        # Adapt to current schema (no-op for current version; upgrades older ones).
        snapshot_json = adapt_snapshot(snapshot_json)
        raw_questions = questions_from_snapshot(snapshot_json)

        class _SnapshotQuestion:
            """Thin wrapper so snapshot question dicts work like ORM instances."""
            __slots__ = ("id", "order", "prompt", "question_type", "choices",
                         "correct_answer", "grading_config", "points")

            def __init__(self, d: dict):
                self.id = d["id"]
                self.order = d.get("order", 0)
                self.prompt = d.get("prompt", "")
                self.question_type = d["question_type"]
                self.choices = d.get("choices") or []
                self.correct_answer = d.get("correct_answer")
                self.grading_config = d.get("grading_config") or {}
                self.points = d.get("points", 1)

        questions = [_SnapshotQuestion(q) for q in raw_questions]
        q_by_id = {q.id: q for q in questions}
        return questions, q_by_id

    # Live path — legacy behaviour for pre-snapshot attempts.
    # Emit fallback telemetry for sunset monitoring.
    try:
        from .domain.governance_events import emit_fallback_path_used
        aset_id = att.homework.assessment_set_id if att.homework_id else 0
        emit_fallback_path_used(
            attempt_id=att.pk,
            set_id=aset_id,
            context="grading",
        )
    except Exception:
        pass  # telemetry must not block grading

    aset = att.homework.assessment_set
    base_questions = list(
        AssessmentQuestion.objects.filter(assessment_set=aset, is_active=True).order_by("order", "id")
    )
    q_by_id = {q.id: q for q in base_questions}
    return base_questions, q_by_id


@transaction.atomic
def grade_attempt(*, attempt_id: int) -> AssessmentResult | None:
    """
    Idempotent grading transaction.

    SNAPSHOT-AWARE:
      - If att.set_version_id is not None, grades against the immutable snapshot
        pinned at attempt creation — content is guaranteed stable regardless of
        any edits made to the live set after the attempt was started.
      - If att.set_version_id is None (pre-snapshot attempt), falls back to live
        question lookup — legacy behaviour, fully backward compatible.

    Locks the attempt row for the duration of the transaction.
    Duplicate Celery deliveries are handled idempotently.
    """
    # Lock the row first (Postgres rejects FOR UPDATE on the nullable side
    # of an outer join — `homework` and `set_version` are nullable FKs).
    locked_exists = AssessmentAttempt.objects.select_for_update().filter(pk=attempt_id).exists()
    if not locked_exists:
        return None
    att = (
        AssessmentAttempt.objects
        .select_related("homework", "homework__assessment_set", "set_version")
        .filter(pk=attempt_id)
        .first()
    )
    if not att:
        return None
    # Idempotent: duplicate Celery deliveries must not re-enter scoring or bump attempts.
    if att.status == AssessmentAttempt.STATUS_GRADED:
        if att.grading_status != AssessmentAttempt.GRADING_COMPLETED:
            att.grading_status = AssessmentAttempt.GRADING_COMPLETED
            att.save(update_fields=["grading_status"])
        return AssessmentResult.objects.filter(attempt=att).first()
    if att.status != AssessmentAttempt.STATUS_SUBMITTED:
        return AssessmentResult.objects.filter(attempt=att).first()

    att.grading_status = AssessmentAttempt.GRADING_PROCESSING
    att.grading_last_attempt_at = timezone.now()
    att.grading_attempts = int(att.grading_attempts or 0) + 1
    att.grading_error = ""
    att.save(update_fields=["grading_status", "grading_last_attempt_at", "grading_attempts", "grading_error"])

    # Resolve questions (snapshot or live).
    base_questions, q_by_id = _questions_from_attempt(att)

    order_ids = [int(x) for x in (att.question_order or []) if str(x).isdigit()]
    questions = [q_by_id[qid] for qid in order_ids if qid in q_by_id] if order_ids else base_questions

    answers = {
        a.question_id: a
        for a in AssessmentAnswer.objects.filter(attempt=att, question_id__in=q_by_id.keys())
    }

    max_points = Decimal("0")
    score = Decimal("0")
    correct = 0
    total_time = 0

    for q in questions:
        max_points += Decimal(str(q.points or 0))
        a = answers.get(q.id)
        total_time += int(getattr(a, "time_spent_seconds", 0) or 0)
        ok = False
        if a is not None:
            ok = grade_answer(
                question_type=q.question_type,
                correct_answer=q.correct_answer,
                answer=a.answer,
                config=q.grading_config or {},
            )
            a.is_correct = ok
            a.points_awarded = Decimal(str(q.points or 0)) if ok else Decimal("0")
            a.save(update_fields=["is_correct", "points_awarded", "updated_at"])
        if ok:
            correct += 1
            score += Decimal(str(q.points or 0))

    total_q = len(questions)
    percent = Decimal("0")
    if max_points > 0:
        percent = (score / max_points) * Decimal("100")

    res, _ = AssessmentResult.objects.update_or_create(
        attempt=att,
        defaults={
            "score_points": score,
            "max_points": max_points,
            "percent": percent,
            "correct_count": correct,
            "total_questions": total_q,
            "graded_at": timezone.now(),
        },
    )

    att.status = AssessmentAttempt.STATUS_GRADED
    att.total_time_seconds = max(int(att.total_time_seconds or 0), total_time)
    att.grading_status = AssessmentAttempt.GRADING_COMPLETED
    att.save(update_fields=["status", "total_time_seconds", "grading_status"])

    AssessmentAttemptAuditEvent.objects.create(
        attempt=att,
        actor=None,
        event_type=AssessmentAttemptAuditEvent.EVENT_GRADED,
        payload={
            "percent": str(percent),
            "async": True,
            "snapshot_graded": att.set_version_id is not None,
        },
    )
    return res
