from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .mitigation import apply_mitigation_for_pattern
from .ops_alerts import deliver_ops_alert
from .rate_sliding import sliding_window_increment_and_count

logger = logging.getLogger("ops.assessments.homework_abuse")


def _bucket_ts(window_seconds: int) -> int:
    return int(time.time()) // window_seconds


def _incr_window(*, key: str, window_seconds: int, ttl: int) -> int:
    """Fixed time buckets (fallback when Redis ZSET sliding is unavailable)."""
    try:
        if cache.add(key, 1, timeout=ttl):
            return 1
        try:
            return int(cache.incr(key))
        except ValueError:
            cache.set(key, 1, timeout=ttl)
            return 1
    except Exception:
        return 0


def _count_sliding_or_fixed(*, sw_key: str, fixed_key: str, window_seconds: int, ttl: int) -> tuple[int, bool]:
    """
    Prefer true sliding window (Redis ZSET). Fall back to fixed buckets via Django cache.
    Returns (count, used_sliding_window).
    """
    c, used = sliding_window_increment_and_count(key=sw_key, window_seconds=window_seconds)
    if used:
        return c, True
    b = _bucket_ts(window_seconds)
    n = _incr_window(key=f"{fixed_key}:{b}", window_seconds=window_seconds, ttl=ttl)
    return n, False


def evaluate_abuse_after_assignment(
    *,
    actor_id: int | None,
    classroom_id: int,
    actor_role: str | None = None,
    actor_is_global_staff: bool = False,
) -> dict[str, Any]:
    """
    After a successful homework assignment audit row, update sliding-window counters and alert on abuse.

    Uses Redis sorted sets when REDIS_URL is a redis:// URL; otherwise fixed cache buckets.
    """
    window = int(getattr(settings, "ASSESSMENT_HW_ABUSE_WINDOW_SECONDS", 300) or 300)
    window = max(60, min(3600, window))
    ttl = window * 2

    user_thr = int(getattr(settings, "ASSESSMENT_HW_ABUSE_ALERT_USER_COUNT", 25) or 25)
    class_thr = int(getattr(settings, "ASSESSMENT_HW_ABUSE_ALERT_CLASS_COUNT", 80) or 80)
    global_thr = int(getattr(settings, "ASSESSMENT_HW_ABUSE_ALERT_GLOBAL_COUNT", 400) or 400)

    b = _bucket_ts(window)
    alerts: list[dict[str, Any]] = []

    g_n, g_sl = _count_sliding_or_fixed(
        sw_key="assess:sw:hw:global",
        fixed_key="assess:hw_abuse:global",
        window_seconds=window,
        ttl=ttl,
    )
    if global_thr > 0 and g_n >= global_thr:
        fired_g = f"assess:hw_abuse:fired:global:{b}"
        if cache.add(fired_g, True, timeout=ttl):
            alerts.append(
                {
                    "kind": "global_assignment_spike",
                    "count": g_n,
                    "threshold": global_thr,
                    "window_s": window,
                    "bucket": b,
                    "sliding_window": g_sl,
                }
            )

    c_n, c_sl = _count_sliding_or_fixed(
        sw_key=f"assess:sw:hw:class:{classroom_id}",
        fixed_key=f"assess:hw_abuse:class:{classroom_id}",
        window_seconds=window,
        ttl=ttl,
    )
    if class_thr > 0 and c_n >= class_thr:
        fired_c = f"assess:hw_abuse:fired:class:{classroom_id}:{b}"
        if cache.add(fired_c, True, timeout=ttl):
            alerts.append(
                {
                    "kind": "classroom_assignment_spike",
                    "classroom_id": classroom_id,
                    "count": c_n,
                    "threshold": class_thr,
                    "window_s": window,
                    "bucket": b,
                    "sliding_window": c_sl,
                }
            )

    if actor_id:
        u_n, u_sl = _count_sliding_or_fixed(
            sw_key=f"assess:sw:hw:user:{actor_id}",
            fixed_key=f"assess:hw_abuse:user:{actor_id}",
            window_seconds=window,
            ttl=ttl,
        )
        if user_thr > 0 and u_n >= user_thr:
            fired_u = f"assess:hw_abuse:fired:user:{actor_id}:{b}"
            if cache.add(fired_u, True, timeout=ttl):
                alerts.append(
                    {
                        "kind": "user_assignment_spike",
                        "user_id": actor_id,
                        "count": u_n,
                        "threshold": user_thr,
                        "window_s": window,
                        "bucket": b,
                        "sliding_window": u_sl,
                    }
                )

    if not alerts:
        return {"ok": True}

    cooldown = int(getattr(settings, "CLASSROOM_ALERT_COOLDOWN_SECONDS", 900) or 900)
    cooldown = max(60, min(24 * 3600, cooldown))

    for a in alerts:
        bucket = a.get("bucket", b)
        fp = (
            "assessments_hw_abuse:"
            + a["kind"]
            + ":"
            + str(a.get("classroom_id") or a.get("user_id") or "global")
            + ":"
            + str(bucket)
        )
        if cache.get(fp):
            continue
        cache.set(fp, True, timeout=cooldown)

        mit = apply_mitigation_for_pattern(a, actor_role=actor_role, actor_is_global_staff=actor_is_global_staff)

        payload = {
            "type": "assessments.homework_assignment_abuse",
            "pattern": a,
            "mitigation": mit,
            "server_time": timezone.now().isoformat(),
        }
        deliver_ops_alert(
            payload=payload,
            fingerprint=fp,
            source="homework_abuse",
            mitigation=mit if mit.get("applied") else None,
        )

    return {"ok": False, "alerts": alerts}


def evaluate_abuse_from_db_recent_window() -> dict[str, Any]:
    """
    Periodic backstop: count assignments in the last N minutes from audit table (survives cache loss).
    """
    from datetime import timedelta

    from django.db.models import Count

    from .models import AssessmentHomeworkAuditEvent

    minutes = int(getattr(settings, "ASSESSMENT_HW_ABUSE_DB_LOOKBACK_MINUTES", 5) or 5)
    minutes = max(1, min(60, minutes))
    since = timezone.now() - timedelta(minutes=minutes)

    total = AssessmentHomeworkAuditEvent.objects.filter(
        event_type=AssessmentHomeworkAuditEvent.EVENT_ASSIGNED,
        created_at__gte=since,
    ).count()

    db_thr = int(getattr(settings, "ASSESSMENT_HW_ABUSE_DB_GLOBAL_THRESHOLD", 500) or 500)
    if total < db_thr:
        return {"ok": True, "total": total, "minutes": minutes}

    window = minutes * 60
    b = int(time.time()) // max(60, window)
    fp = f"assessments_hw_abuse:db_global:{minutes}m:{b}"
    if cache.get(fp):
        return {"ok": False, "deduped": True, "total": total}

    cooldown = int(getattr(settings, "CLASSROOM_ALERT_COOLDOWN_SECONDS", 900) or 900)
    cache.set(fp, True, timeout=max(60, cooldown))
    payload = {
        "type": "assessments.homework_assignment_abuse_db",
        "total_assignments": total,
        "threshold": db_thr,
        "window_minutes": minutes,
        "server_time": timezone.now().isoformat(),
    }
    deliver_ops_alert(
        payload=payload,
        fingerprint=fp,
        source="homework_abuse_db",
        alert_type="assessments.homework_assignment_abuse_db",
    )

    top_users = list(
        AssessmentHomeworkAuditEvent.objects.filter(
            event_type=AssessmentHomeworkAuditEvent.EVENT_ASSIGNED,
            created_at__gte=since,
            actor_id__isnull=False,
        )
        .values("actor_id")
        .annotate(n=Count("id"))
        .order_by("-n")[:5]
    )
    top_classes = list(
        AssessmentHomeworkAuditEvent.objects.filter(
            event_type=AssessmentHomeworkAuditEvent.EVENT_ASSIGNED,
            created_at__gte=since,
        )
        .values("classroom_id")
        .annotate(n=Count("id"))
        .order_by("-n")[:5]
    )
    logger.critical(
        "homework assignment abuse (db) total=%s top_users=%s top_classes=%s",
        total,
        top_users,
        top_classes,
    )

    return {"ok": False, "total": total, "top_users": top_users, "top_classes": top_classes}
