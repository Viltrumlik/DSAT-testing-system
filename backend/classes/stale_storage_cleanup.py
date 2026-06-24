"""
Retry deletion of homework files recorded in StaleStorageBlob; alert on chronic failures.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Avg, Count, Max, Sum
from django.utils import timezone

from .alerting import notify_ops_critical
from .metrics import get_homework_submit_metrics_snapshot
from .models import HomeworkStagedUpload, StaleStorageBlob

logger = logging.getLogger("classes.stale_storage_cleanup")

# After this many consecutive failed attempts, emit CRITICAL once per row (see alert_logged_at).
ALERT_AFTER_FAILURES = int(getattr(settings, "CLASSROOM_STALE_STORAGE_ALERT_AFTER", 8))


def run_stale_storage_cleanup(*, batch_size: int = 200) -> dict[str, int]:
    """
    Process up to ``batch_size`` rows. Returns counts for metrics/logging.
    """
    now = timezone.now()
    processed = 0
    deleted_rows = 0
    failed = 0

    rows = list(StaleStorageBlob.objects.order_by("created_at")[:batch_size])
    for row in rows:
        processed += 1
        path = row.storage_name
        pk = row.pk
        row.retry_count += 1
        row.last_attempt_at = now
        try:
            if path and default_storage.exists(path):
                default_storage.delete(path)
            if path and default_storage.exists(path):
                raise RuntimeError("storage still exists after delete")
            row.delete()
            deleted_rows += 1
            continue
        except Exception as e:
            row.consecutive_failures += 1
            row.last_error = str(e)[:4000]
            row.save(
                update_fields=[
                    "retry_count",
                    "consecutive_failures",
                    "last_error",
                    "last_attempt_at",
                ]
            )
            failed += 1
            if row.consecutive_failures >= ALERT_AFTER_FAILURES and row.alert_logged_at is None:
                notify_ops_critical(
                    "stale_storage_blob_chronic_failure",
                    f"Homework stale blob delete failed {row.consecutive_failures} times (path={path!r}).",
                    extra={
                        "stale_storage_blob_id": pk,
                        "storage_path": path,
                        "consecutive_failures": row.consecutive_failures,
                        "last_error": (row.last_error or "")[:2000],
                    },
                )
                StaleStorageBlob.objects.filter(pk=pk).update(alert_logged_at=now)

    return {
        "processed": processed,
        "deleted_rows": deleted_rows,
        "failed_still_tracked": failed,
    }


def prune_homework_staged_upload_records(*, retention_days: int | None = None) -> dict[str, int]:
    """
    Delete old ``HomeworkStagedUpload`` rows in ``attached`` status (DB bookkeeping only; files are owned by ``SubmissionFile``).

    Retention is controlled by ``CLASSROOM_HOMEWORK_STAGED_RETENTION_DAYS`` (default 30).
    """
    days = retention_days
    if days is None:
        days = int(getattr(settings, "CLASSROOM_HOMEWORK_STAGED_RETENTION_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=days)
    qs = HomeworkStagedUpload.objects.filter(
        status=HomeworkStagedUpload.STATUS_ATTACHED,
        updated_at__lt=cutoff,
    )
    deleted, breakdown = qs.delete()
    return {"deleted_rows": deleted, "per_model": breakdown}


def get_homework_storage_observability() -> dict:
    """
    Metrics for stale homework blob cleanup (dashboards / alerting).
    """
    now = timezone.now()
    qs = StaleStorageBlob.objects.all()
    backlog = qs.count()
    agg = qs.aggregate(
        total_retries=Sum("retry_count"),
        total_consecutive=Sum("consecutive_failures"),
        avg_consecutive=Avg("consecutive_failures"),
        max_consecutive=Max("consecutive_failures"),
    )
    recent = qs.filter(last_attempt_at__gte=now - timedelta(hours=24)).count()
    alerted = qs.exclude(alert_logged_at__isnull=True).count()
    failure_rate = (recent / backlog) if backlog else 0.0
    staged_staging = HomeworkStagedUpload.objects.filter(status=HomeworkStagedUpload.STATUS_STAGING).count()
    staged_abandoned = HomeworkStagedUpload.objects.filter(status=HomeworkStagedUpload.STATUS_ABANDONED).count()
    staged_attached = HomeworkStagedUpload.objects.filter(status=HomeworkStagedUpload.STATUS_ATTACHED).count()
    return {
        "stale_blob_backlog_count": backlog,
        "stale_blob_total_retry_count": int(agg["total_retries"] or 0),
        "stale_blob_sum_consecutive_failures": int(agg["total_consecutive"] or 0),
        "stale_blob_avg_consecutive_failures": float(agg["avg_consecutive"] or 0),
        "stale_blob_max_consecutive_failures": int(agg["max_consecutive"] or 0),
        "stale_blob_attempts_last_24h": recent,
        "stale_blob_rows_with_alert_logged": alerted,
        "stale_blob_recent_attempt_ratio_vs_backlog": round(failure_rate, 4),
        "homework_staged_upload_staging_count": staged_staging,
        "homework_staged_upload_attached_count": staged_attached,
        "homework_staged_upload_abandoned_count": staged_abandoned,
        "homework_submit_metrics": get_homework_submit_metrics_snapshot(),
    }
