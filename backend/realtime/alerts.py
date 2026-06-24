"""
Threshold checks for logs / external alerting (Prometheus Alertmanager consumes metrics).

Call from metrics endpoints; uses cumulative counters — ratios are approximate.
"""

from __future__ import annotations

import logging

from django.conf import settings

from .metrics import get_counter

logger = logging.getLogger("realtime.alerts")


def evaluate_realtime_thresholds() -> list[dict]:
    """
    Returns a list of fired alert dicts for structured logging.
    Thresholds are configurable via settings (see config.settings REALTIME_ALERT_*).
    """
    fired: list[dict] = []

    resync = get_counter("resync_payloads")
    sse_total = max(1, get_counter("sse_events_from_redis") + get_counter("sse_events_from_db"))
    resync_ratio = resync / sse_total

    max_resync = float(getattr(settings, "REALTIME_ALERT_MAX_RESYNC_RATIO", 0.12))
    if resync_ratio > max_resync and resync >= int(getattr(settings, "REALTIME_ALERT_MIN_RESYNC_EVENTS", 5)):
        fired.append(
            {
                "name": "realtime_high_resync_rate",
                "resync_ratio": round(resync_ratio, 4),
                "threshold": max_resync,
                "resync_payloads": resync,
            }
        )

    deduped = get_counter("events_dedupe_suppressed")
    persisted = get_counter("events_persisted_total")
    dedupe_ratio = deduped / max(1, deduped + persisted)
    max_dedupe = float(getattr(settings, "REALTIME_ALERT_MAX_DEDUPE_SUPPRESSION_RATIO", 0.85))
    if dedupe_ratio > max_dedupe and deduped >= int(getattr(settings, "REALTIME_ALERT_MIN_DEDUPE_EVENTS", 50)):
        fired.append(
            {
                "name": "realtime_high_dedupe_suppression",
                "dedupe_ratio": round(dedupe_ratio, 4),
                "threshold": max_dedupe,
                "events_dedupe_suppressed": deduped,
            }
        )

    redis_fail = get_counter("redis_publish_failures")
    redis_ok = get_counter("events_redis_published")
    if redis_fail >= int(getattr(settings, "REALTIME_ALERT_MIN_REDIS_FAILURES", 3)):
        fail_ratio = redis_fail / max(1, redis_fail + redis_ok)
        max_fail = float(getattr(settings, "REALTIME_ALERT_MAX_REDIS_FAILURE_RATIO", 0.05))
        if fail_ratio > max_fail:
            fired.append(
                {
                    "name": "realtime_redis_publish_failures",
                    "failure_ratio": round(fail_ratio, 4),
                    "threshold": max_fail,
                    "redis_publish_failures": redis_fail,
                }
            )

    for a in fired:
        logger.warning("realtime_alert %s", a)

    return fired
