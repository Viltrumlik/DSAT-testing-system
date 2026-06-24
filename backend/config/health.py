from __future__ import annotations

from dataclasses import dataclass

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from assessments.models import HomeworkAssignment
from exams.models import TestAttempt
from core.drills import env_flag, maybe_sleep_ms


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    details: dict


def _pending_migrations() -> list[str]:
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    # Plan is a list of (migration, backwards) tuples; backwards=False means pending forward migration.
    out = []
    for mig, backwards in plan:
        if backwards:
            continue
        out.append(f"{mig.app_label}.{mig.name}")
    return out


def _constraint_exists(constraint_name: str) -> bool:
    # Best-effort introspection; Postgres and SQLite both report constraints via get_constraints.
    try:
        for table in ("test_attempts", "assessment_homework_assignments"):
            constraints = connection.introspection.get_constraints(connection.cursor(), table)
            if constraint_name in constraints:
                return True
    except Exception:
        return False
    return False


def _dup_active_attempt_groups() -> int:
    return (
        TestAttempt.objects.filter(is_completed=False)
        .exclude(current_state=TestAttempt.STATE_ABANDONED)
        .values("student_id", "practice_test_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .count()
    )


def _dup_homework_groups() -> int:
    return (
        HomeworkAssignment.objects.values("classroom_id", "assessment_set_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .count()
    )


class LiveHealthView(View):
    def get(self, request):
        maybe_sleep_ms("DRILL_DB_SLOW_MS")
        return JsonResponse(
            {"ok": True, "ts": timezone.now().isoformat()},
            status=200,
        )


class ReadyHealthView(View):
    """
    Hybrid readiness:
    - Fail hard (500): pending migrations OR missing critical constraints.
    - Warn only (200 + warnings): dup active attempts, dup homework groups.
    """

    def get(self, request):
        maybe_sleep_ms("DRILL_DB_SLOW_MS")
        pending = _pending_migrations()
        if env_flag("DRILL_WRONG_MIGRATION"):
            pending = list(pending) + ["DRILL.wrong_migration_deployed"]
        constraints = {
            "uniq_active_attempt_per_student_test": _constraint_exists("uniq_active_attempt_per_student_test"),
            "uniq_assessment_hw_classroom_set": _constraint_exists("uniq_assessment_hw_classroom_set"),
        }
        hard_fail = bool(pending) or not all(constraints.values())

        warnings = {
            "duplicate_active_attempt_groups": _dup_active_attempt_groups(),
            "duplicate_homework_groups": _dup_homework_groups(),
        }

        payload = {
            "ok": not hard_fail,
            "ts": timezone.now().isoformat(),
            "hard_fail_reasons": {
                "pending_migrations": pending,
                "missing_constraints": [k for k, v in constraints.items() if not v],
            },
            "warnings": warnings,
        }
        return JsonResponse(payload, status=500 if hard_fail else 200)

