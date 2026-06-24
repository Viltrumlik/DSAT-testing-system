"""Prometheus text exposition for assessment grading ops (no extra dependencies)."""

from __future__ import annotations

from django.utils import timezone

from .models import AssessmentAttempt
from .worker_metrics import get_celery_worker_snapshot


def render_assessments_prometheus_text() -> str:
    """
    Gauges for current state + counters where we have monotonic data.
    Prefer using Prometheus rate()/irate() on counters from scrape deltas.
    """
    now = timezone.now()

    pending = AssessmentAttempt.objects.filter(
        status=AssessmentAttempt.STATUS_SUBMITTED,
        grading_status=AssessmentAttempt.GRADING_PENDING,
    ).count()
    processing = AssessmentAttempt.objects.filter(
        status=AssessmentAttempt.STATUS_SUBMITTED,
        grading_status=AssessmentAttempt.GRADING_PROCESSING,
    ).count()
    failed = AssessmentAttempt.objects.filter(grading_status=AssessmentAttempt.GRADING_FAILED).count()

    wm = get_celery_worker_snapshot()

    lines: list[str] = [
        "# HELP assessments_grading_pending Pending attempts awaiting grading (DB-derived).",
        "# TYPE assessments_grading_pending gauge",
        f"assessments_grading_pending {pending}",
        "# HELP assessments_grading_processing Attempts currently marked processing (DB-derived).",
        "# TYPE assessments_grading_processing gauge",
        f"assessments_grading_processing {processing}",
        "# HELP assessments_grading_failed_total Attempts currently in failed status (DB-derived).",
        "# TYPE assessments_grading_failed_total gauge",
        f"assessments_grading_failed_total {failed}",
        "# HELP assessments_workers_active Number of visible Celery workers (best-effort inspect).",
        "# TYPE assessments_workers_active gauge",
        f"assessments_workers_active {int(wm.get('workers') or 0)}",
        "# HELP assessments_worker_active_tasks Number of active Celery tasks across workers.",
        "# TYPE assessments_worker_active_tasks gauge",
        f"assessments_worker_active_tasks {int(wm.get('active_tasks') or 0)}",
        "# HELP assessments_worker_reserved_tasks Number of reserved Celery tasks across workers.",
        "# TYPE assessments_worker_reserved_tasks gauge",
        f"assessments_worker_reserved_tasks {int(wm.get('reserved_tasks') or 0)}",
        "# HELP assessments_worker_scheduled_tasks Number of scheduled Celery tasks across workers.",
        "# TYPE assessments_worker_scheduled_tasks gauge",
        f"assessments_worker_scheduled_tasks {int(wm.get('scheduled_tasks') or 0)}",
        "# HELP assessments_worker_active_runtime_seconds_avg Average runtime of active tasks (s).",
        "# TYPE assessments_worker_active_runtime_seconds_avg gauge",
        f"assessments_worker_active_runtime_seconds_avg {float(wm.get('active_runtime_seconds', {}).get('avg') or 0.0)}",
        "# HELP assessments_worker_active_runtime_seconds_max Max runtime of active tasks (s).",
        "# TYPE assessments_worker_active_runtime_seconds_max gauge",
        f"assessments_worker_active_runtime_seconds_max {float(wm.get('active_runtime_seconds', {}).get('max') or 0.0)}",
        "# HELP assessments_server_time Unix time of this scrape.",
        "# TYPE assessments_server_time gauge",
        f"assessments_server_time {int(now.timestamp())}",
    ]

    return "\n".join(lines) + "\n"

