"""Prometheus text exposition for assessment homework integrity counters (no extra dependencies)."""

from __future__ import annotations

from django.utils import timezone

from .metrics import get_counter


def render_assessments_homework_prometheus_text() -> str:
    lines: list[str] = [
        "# HELP assessments_homework_duplicate_prevented_total Duplicate homework assigns prevented by DB constraint retry.",
        "# TYPE assessments_homework_duplicate_prevented_total counter",
        f"assessments_homework_duplicate_prevented_total {get_counter('homework_duplicate_prevented')}",
        "# HELP assessments_integrity_repairs_applied_total Integrity repair mutations applied (best-effort).",
        "# TYPE assessments_integrity_repairs_applied_total counter",
        f"assessments_integrity_repairs_applied_total {get_counter('integrity_repairs_applied')}",
        "# HELP invalid_selection_recovered_total Invalid persisted selection recovered by UI logic (best-effort ping).",
        "# TYPE invalid_selection_recovered_total counter",
        f"invalid_selection_recovered_total {get_counter('invalid_selection_recovered_total')}",
        "# HELP stale_id_blocked_total Stale IDs blocked before sending mutating requests (best-effort ping).",
        "# TYPE stale_id_blocked_total counter",
        f"stale_id_blocked_total {get_counter('stale_id_blocked_total')}",
        "# HELP builder_refetch_recovery_total Builder refetch recoveries triggered by stale list/selection (best-effort ping).",
        "# TYPE builder_refetch_recovery_total counter",
        f"builder_refetch_recovery_total {get_counter('builder_refetch_recovery_total')}",
        "# HELP assessments_metrics_generated_at Unix timestamp when metrics rendered.",
        "# TYPE assessments_metrics_generated_at gauge",
        f"assessments_metrics_generated_at {int(timezone.now().timestamp())}",
    ]
    return "\n".join(lines) + "\n"

