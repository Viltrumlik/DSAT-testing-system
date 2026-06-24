from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import RealtimeEvent
from .services import persist_realtime_batch

logger = logging.getLogger("realtime.tasks")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def fanout_realtime_events(self, rows: list[dict]) -> int:
    """
    Async fan-out for realtime outbox.

    rows: [{user_id, event_type, payload, dedupe_key, priority?}]
    """
    if not rows:
        return 0
    t0 = timezone.now()
    inserted, suppressed = persist_realtime_batch(rows)
    dt_ms = int((timezone.now() - t0).total_seconds() * 1000)
    try:
        from .metrics import incr as metric_incr

        metric_incr("celery_fanout_latency_ms_total", dt_ms)
        metric_incr("celery_fanout_batches")
    except Exception:
        pass
    logger.info(
        "fanout_realtime_events in=%s inserted=%s suppressed=%s users=%s",
        len(rows),
        inserted,
        suppressed,
        len({int(r["user_id"]) for r in rows}),
    )
    return inserted


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def cleanup_realtime_events(self, *, older_than_hours: int = 24, limit: int = 20000) -> int:
    cutoff = timezone.now() - timedelta(hours=int(older_than_hours))
    qs = RealtimeEvent.objects.filter(created_at__lt=cutoff).order_by("id").values_list("id", flat=True)[: int(limit)]
    ids = list(qs)
    if not ids:
        return 0
    deleted, _ = RealtimeEvent.objects.filter(id__in=ids).delete()
    logger.info("cleanup_realtime_events deleted=%s cutoff=%s", deleted, cutoff.isoformat())
    return deleted
