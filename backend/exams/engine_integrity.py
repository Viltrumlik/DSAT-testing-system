from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import MockExam, Module, PracticeTest, TestAttempt, ensure_full_mock_practice_test_modules


@dataclass(frozen=True)
class IntegrityFinding:
    code: str
    detail: str


def required_module_orders_for_test(test: PracticeTest) -> tuple[int, ...]:
    """
    For SAT engine purposes:
    - normal sections: always 1,2
    - midterm: 1, and 2 only if midterm_module_count >= 2
    """
    mock = getattr(test, "mock_exam", None)
    if mock and getattr(mock, "kind", None) == MockExam.KIND_MIDTERM:
        cnt = int(getattr(mock, "midterm_module_count", 2) or 2)
        return (1, 2) if cnt >= 2 else (1,)
    return (1, 2)


def infer_state_from_attempt(attempt: TestAttempt) -> str:
    """
    Best-effort inference for repair flows when the persisted state is impossible.
    """
    if attempt.is_completed:
        return TestAttempt.STATE_COMPLETED

    cm = getattr(attempt, "current_module", None)
    if cm is not None:
        try:
            order = int(getattr(cm, "module_order", 0) or 0)
        except (TypeError, ValueError):
            order = 0
        if order == 2:
            return TestAttempt.STATE_MODULE_2_ACTIVE
        if order == 1:
            return TestAttempt.STATE_MODULE_1_ACTIVE

    # Fall back on completed_modules / module_answers.
    try:
        completed_orders = set(attempt.completed_modules.values_list("module_order", flat=True))
    except Exception:
        completed_orders = set()

    if 2 in completed_orders:
        if getattr(attempt, "scoring_started_at", None) or getattr(attempt, "module_2_submitted_at", None):
            return TestAttempt.STATE_SCORING
        return TestAttempt.STATE_MODULE_2_SUBMITTED
    if 1 in completed_orders:
        return TestAttempt.STATE_MODULE_1_SUBMITTED

    try:
        answered_ids = [int(x) for x in (attempt.module_answers or {}).keys()]
    except Exception:
        answered_ids = []
    if answered_ids:
        orders = set(
            Module.objects.filter(id__in=answered_ids).values_list("module_order", flat=True)
        )
        if 2 in orders:
            if getattr(attempt, "scoring_started_at", None) or getattr(attempt, "module_2_submitted_at", None):
                return TestAttempt.STATE_SCORING
            return TestAttempt.STATE_MODULE_2_SUBMITTED
        if 1 in orders:
            return TestAttempt.STATE_MODULE_1_SUBMITTED

    return TestAttempt.STATE_NOT_STARTED


def audit_attempt_invariants(attempt: TestAttempt) -> list[IntegrityFinding]:
    out: list[IntegrityFinding] = []

    st = str(getattr(attempt, "current_state", "") or "")
    cm = getattr(attempt, "current_module", None)
    cm_order = getattr(cm, "module_order", None) if cm else None

    if st == TestAttempt.STATE_COMPLETED and not attempt.is_completed:
        out.append(IntegrityFinding("attempt.completed_flag_missing", "current_state=COMPLETED but is_completed=False"))
    if attempt.is_completed and st != TestAttempt.STATE_COMPLETED:
        out.append(IntegrityFinding("attempt.state_not_completed", "is_completed=True but current_state!=COMPLETED"))

    if st == TestAttempt.STATE_MODULE_1_ACTIVE and cm_order != 1:
        out.append(IntegrityFinding("attempt.m1_active_wrong_current_module", f"expected current_module.order=1, got {cm_order}"))
    if st == TestAttempt.STATE_MODULE_2_ACTIVE and cm_order != 2:
        out.append(IntegrityFinding("attempt.m2_active_wrong_current_module", f"expected current_module.order=2, got {cm_order}"))
    if st in (TestAttempt.STATE_SCORING, TestAttempt.STATE_COMPLETED) and cm is not None:
        out.append(IntegrityFinding("attempt.scoring_or_completed_has_current_module", "current_module should be NULL in scoring/completed"))

    # Timestamp sanity (best-effort)
    if st in (TestAttempt.STATE_MODULE_2_ACTIVE, TestAttempt.STATE_MODULE_2_SUBMITTED, TestAttempt.STATE_SCORING, TestAttempt.STATE_COMPLETED):
        if not getattr(attempt, "module_1_started_at", None):
            out.append(IntegrityFinding("attempt.m2_without_m1_started_at", "module_1_started_at missing while in/after module 2"))

    return out


def autoheal_attempt_for_runtime(attempt: TestAttempt) -> list[IntegrityFinding]:
    """
    Runtime-only auto-heal called inside select_for_update() transactions.
    Must be safe, idempotent, and minimal.
    """
    findings = audit_attempt_invariants(attempt)
    if not findings:
        return []

    updates: set[str] = set()
    now = timezone.now()

    # Normalize COMPLETED flag/state mismatch.
    if attempt.is_completed and attempt.current_state != TestAttempt.STATE_COMPLETED:
        attempt.current_state = TestAttempt.STATE_COMPLETED
        attempt.completed_at = attempt.completed_at or now
        attempt.current_module = None
        updates.update({"current_state", "completed_at", "current_module"})
    if attempt.current_state == TestAttempt.STATE_COMPLETED and not attempt.is_completed:
        attempt.is_completed = True
        attempt.completed_at = attempt.completed_at or now
        attempt.current_module = None
        updates.update({"is_completed", "completed_at", "current_module"})

    # If we are "active" but current_module is missing/wrong, try to snap to the canonical module row.
    if attempt.current_state in (TestAttempt.STATE_MODULE_1_ACTIVE, TestAttempt.STATE_MODULE_2_ACTIVE):
        ensure_full_mock_practice_test_modules(attempt.practice_test)
        desired_order = 1 if attempt.current_state == TestAttempt.STATE_MODULE_1_ACTIVE else 2
        desired = attempt.practice_test.modules.filter(module_order=desired_order).order_by("id").first()
        if desired:
            attempt.current_module = desired
            o = int(getattr(desired, "module_order", 0) or 0)
            if o == 1:
                attempt.module_1_started_at = getattr(attempt, "module_1_started_at", None) or now
                attempt.current_module_start_time = attempt.module_1_started_at
            elif o == 2:
                attempt.module_2_started_at = getattr(attempt, "module_2_started_at", None) or now
                attempt.current_module_start_time = attempt.module_2_started_at
            updates.update(
                {"current_module", "current_module_start_time", "module_1_started_at", "module_2_started_at"}
            )

    # If MODULE_2_ACTIVE but Module 2 has zero questions (single-module pastpaper),
    # promote directly to SCORING so the student isn't stuck on an empty module.
    if attempt.current_state == TestAttempt.STATE_MODULE_2_ACTIVE:
        m2 = attempt.practice_test.modules.filter(module_order=2).order_by("id").first()
        if m2 and m2.questions.count() == 0:
            attempt.current_state = TestAttempt.STATE_SCORING
            attempt.current_module = None
            attempt.current_module_start_time = None
            attempt.module_2_submitted_at = attempt.module_2_submitted_at or now
            attempt.scoring_started_at = attempt.scoring_started_at or now
            if not attempt.completed_modules.filter(pk=m2.pk).exists():
                attempt.completed_modules.add(m2)
            updates.update({
                "current_state", "current_module", "current_module_start_time",
                "module_2_submitted_at", "scoring_started_at",
            })
            logger.info(
                "autoheal_empty_m2_to_scoring attempt_id=%s",
                attempt.pk,
            )

    # In scoring/completed, force current_module null.
    if attempt.current_state in (TestAttempt.STATE_SCORING, TestAttempt.STATE_COMPLETED) and attempt.current_module_id:
        attempt.current_module = None
        updates.add("current_module")

    if updates:
        attempt.version_number = int(attempt.version_number or 0) + 1
        updates.add("version_number")
        attempt.save(update_fields=list(updates | {"updated_at"}))

    return findings

