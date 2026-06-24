from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AssessmentAttempt, AssessmentAttemptAuditEvent
from .async_tasks import grade_attempt_task


@shared_task
def abandon_inactive_attempts() -> dict:
    """
    Periodic reliability job: mark in_progress attempts abandoned after inactivity.
    Uses last_activity_at when available; falls back to started_at.
    """
    timeout_s = int(getattr(settings, "ASSESSMENT_ATTEMPT_INACTIVITY_TIMEOUT_SECONDS", 3600) or 3600)
    timeout_s = max(300, min(7 * 24 * 3600, timeout_s))
    cutoff = timezone.now() - timedelta(seconds=timeout_s)

    qs = AssessmentAttempt.objects.filter(status=AssessmentAttempt.STATUS_IN_PROGRESS).filter(
        Q(last_activity_at__lte=cutoff) | Q(last_activity_at__isnull=True, started_at__lte=cutoff)
    )

    # Evaluate candidates first (small batches) to avoid long locks.
    ids = list(qs.values_list("id", flat=True)[:500])
    abandoned = 0
    now = timezone.now()
    for pk in ids:
        with transaction.atomic():
            att = AssessmentAttempt.objects.select_for_update().filter(pk=pk).first()
            if not att or att.status != AssessmentAttempt.STATUS_IN_PROGRESS:
                continue
            last = att.last_activity_at or att.started_at
            if last and last > cutoff:
                continue
            att.status = AssessmentAttempt.STATUS_ABANDONED
            att.abandoned_at = now
            att.last_activity_at = now
            att.save(update_fields=["status", "abandoned_at", "last_activity_at"])
            AssessmentAttemptAuditEvent.objects.create(
                attempt=att,
                actor=None,
                event_type=AssessmentAttemptAuditEvent.EVENT_TIMEOUT_ABANDONED,
                payload={"timeout_seconds": timeout_s},
            )
            abandoned += 1
    return {"abandoned": abandoned, "checked": len(ids), "timeout_seconds": timeout_s}


@shared_task
def prune_assessment_audit_events() -> dict:
    """
    Retention job for audit events. Default keeps 180 days.
    For large scale, switch to table partitioning by month and drop old partitions instead.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.conf import settings

    days = int(getattr(settings, "ASSESSMENT_AUDIT_RETENTION_DAYS", 180) or 180)
    days = max(7, min(3650, days))
    cutoff = timezone.now() - timedelta(days=days)
    from .models import AssessmentAttemptAuditEvent

    qs = AssessmentAttemptAuditEvent.objects.filter(created_at__lt=cutoff)
    # Delete in chunks to avoid long transactions.
    ids = list(qs.values_list("id", flat=True)[:5000])
    deleted = 0
    if ids:
        deleted, _ = AssessmentAttemptAuditEvent.objects.filter(id__in=ids).delete()
    return {"deleted": deleted, "retention_days": days}


@shared_task
def dispatch_pending_grading() -> dict:
    """
    Backpressure-aware dispatcher:
    - Enqueue pending grading attempts in small batches
    - Stop when inflight (pending+processing) exceeds ASSESSMENT_GRADING_MAX_INFLIGHT
    """
    from django.conf import settings
    from django.utils import timezone
    from django.core.cache import cache

    max_inflight = int(getattr(settings, "ASSESSMENT_GRADING_MAX_INFLIGHT", 500) or 500)
    batch = int(getattr(settings, "ASSESSMENT_GRADING_DISPATCH_BATCH", 50) or 50)
    max_per_min = int(getattr(settings, "ASSESSMENT_GRADING_MAX_ENQUEUE_PER_MINUTE", 2000) or 2000)
    max_inflight = max(10, min(100_000, max_inflight))
    batch = max(1, min(2000, batch))
    max_per_min = max(10, min(500_000, max_per_min))

    inflight = AssessmentAttempt.objects.filter(
        status=AssessmentAttempt.STATUS_SUBMITTED,
        grading_status__in=(AssessmentAttempt.GRADING_PENDING, AssessmentAttempt.GRADING_PROCESSING),
    ).count()
    if inflight >= max_inflight:
        return {"enqueued": 0, "inflight": inflight, "max_inflight": max_inflight, "reason": "backpressure"}

    remaining_budget = max(0, max_inflight - inflight)
    to_take = min(batch, remaining_budget)

    # Capacity control: global enqueue budget per minute (shared cache recommended).
    budget_key = f"assessments:grading:enq_budget:{timezone.now().strftime('%Y%m%d%H%M')}"
    used = cache.get(budget_key)
    try:
        used_i = int(used or 0)
    except Exception:
        used_i = 0
    if used_i >= max_per_min:
        return {
            "enqueued": 0,
            "inflight": inflight,
            "max_inflight": max_inflight,
            "batch": batch,
            "max_per_min": max_per_min,
            "used_this_minute": used_i,
            "reason": "capacity_budget",
            "now": timezone.now().isoformat(),
        }
    to_take = min(to_take, max(0, max_per_min - used_i))
    if to_take <= 0:
        return {
            "enqueued": 0,
            "inflight": inflight,
            "max_inflight": max_inflight,
            "batch": batch,
            "max_per_min": max_per_min,
            "used_this_minute": used_i,
            "reason": "capacity_budget",
            "now": timezone.now().isoformat(),
        }
    ids = list(
        AssessmentAttempt.objects.filter(
            status=AssessmentAttempt.STATUS_SUBMITTED,
            grading_status=AssessmentAttempt.GRADING_PENDING,
        )
        .order_by("submitted_at", "id")
        .values_list("id", flat=True)[:to_take]
    )
    enqueued = 0
    for pk in ids:
        grade_attempt_task.delay(int(pk))
        enqueued += 1
    if enqueued:
        try:
            cache.add(budget_key, used_i, timeout=120)
            cache.incr(budget_key, enqueued)
        except Exception:
            pass
    return {
        "enqueued": enqueued,
        "inflight": inflight,
        "max_inflight": max_inflight,
        "batch": batch,
        "max_per_min": max_per_min,
        "used_this_minute": used_i + enqueued,
        "now": timezone.now().isoformat(),
    }


@shared_task
def alert_on_assessment_slo() -> dict:
    """
    SLO-based alerting (best-effort):
    - latency p90
    - failure rate
    - pending backlog age/count
    Alerts are emitted as CRITICAL logs and optionally posted to an ops webhook.
    Dedupe uses default cache with CLASSROOM_ALERT_COOLDOWN_SECONDS.
    """
    import logging
    from django.core.cache import cache
    from django.conf import settings
    from .ops_alerts import deliver_ops_alert

    logger = logging.getLogger("ops.assessments")
    now = timezone.now()
    cooldown = int(getattr(settings, "CLASSROOM_ALERT_COOLDOWN_SECONDS", 900) or 900)
    cooldown = max(60, min(24 * 3600, cooldown))

    # Latency samples from last hour.
    since = now - timezone.timedelta(hours=1)
    res_qs = (
        AssessmentAttempt.objects.filter(
            grading_status=AssessmentAttempt.GRADING_COMPLETED,
            grading_last_attempt_at__gte=since,
        )
        .select_related("result")
        .only("submitted_at", "result__graded_at")[:800]
    )
    lats = []
    for a in res_qs:
        sub = a.submitted_at
        graded_at = getattr(getattr(a, "result", None), "graded_at", None)
        if sub and graded_at:
            lats.append((graded_at - sub).total_seconds())
    lats.sort()
    def p90():
        if not lats:
            return None
        i = int(round((len(lats) - 1) * 0.90))
        return float(lats[max(0, min(len(lats) - 1, i))])

    p90_lat = p90()
    p90_thr = float(getattr(settings, "ASSESSMENT_ALERT_P90_LATENCY_SECONDS", 30.0) or 30.0)

    # Failure rate last hour.
    completed = AssessmentAttempt.objects.filter(
        grading_status=AssessmentAttempt.GRADING_COMPLETED,
        grading_last_attempt_at__gte=since,
    ).count()
    failed = AssessmentAttempt.objects.filter(
        grading_status=AssessmentAttempt.GRADING_FAILED,
        grading_last_attempt_at__gte=since,
    ).count()
    fail_rate = (failed / (failed + completed) * 100.0) if (failed + completed) > 0 else 0.0
    fail_thr = float(getattr(settings, "ASSESSMENT_ALERT_FAILURE_RATE_PCT", 0.5) or 0.5)

    # Pending backlog older than threshold.
    age_s = int(getattr(settings, "ASSESSMENT_ALERT_PENDING_OLDER_THAN_SECONDS", 600) or 600)
    cnt_thr = int(getattr(settings, "ASSESSMENT_ALERT_PENDING_OLDER_THAN_COUNT", 200) or 200)
    cutoff = now - timezone.timedelta(seconds=age_s)
    old_pending = AssessmentAttempt.objects.filter(
        status=AssessmentAttempt.STATUS_SUBMITTED,
        grading_status=AssessmentAttempt.GRADING_PENDING,
        submitted_at__lte=cutoff,
    ).count()

    violations = []
    if p90_lat is not None and p90_lat > p90_thr:
        violations.append({"kind": "latency_p90", "value": p90_lat, "threshold": p90_thr})
    if fail_rate > fail_thr:
        violations.append({"kind": "failure_rate_pct", "value": round(fail_rate, 3), "threshold": fail_thr})
    if old_pending > cnt_thr:
        violations.append({"kind": "old_pending_count", "value": old_pending, "threshold": cnt_thr, "age_seconds": age_s})

    if not violations:
        return {"ok": True}

    fingerprint = "assessments_slo:" + ",".join(v["kind"] for v in violations)
    if cache.get(fingerprint):
        return {"ok": False, "deduped": True, "violations": violations}
    cache.set(fingerprint, True, timeout=cooldown)

    payload = {
        "type": "assessments.slo_violation",
        "violations": violations,
        "window": "1h",
        "server_time": now.isoformat(),
    }
    delivery = deliver_ops_alert(
        payload=payload,
        fingerprint=fingerprint,
        source="slo",
        alert_type="assessments.slo_violation",
    )

    return {"ok": False, "violations": violations, "delivery": delivery}


@shared_task
def alert_homework_assignment_abuse_db() -> dict:
    """
    DB backstop for assignment abuse: counts recent audit rows (survives cache eviction).
    """
    from .homework_abuse import evaluate_abuse_from_db_recent_window

    return evaluate_abuse_from_db_recent_window()


@shared_task
def prune_security_alerts() -> dict:
    """
    Retention for SecurityAlert rows (ops/security alerts).
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from .models import SecurityAlert

    days = int(getattr(settings, "ASSESSMENT_SECURITY_ALERT_RETENTION_DAYS", 180) or 180)
    days = max(7, min(3650, days))
    cutoff = timezone.now() - timedelta(days=days)
    qs = SecurityAlert.objects.filter(created_at__lt=cutoff)
    ids = list(qs.values_list("id", flat=True)[:5000])
    deleted = 0
    if ids:
        deleted, _ = SecurityAlert.objects.filter(id__in=ids).delete()
    return {"deleted": deleted, "retention_days": days}

