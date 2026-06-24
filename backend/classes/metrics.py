"""
Homework submission counters (Redis / shared cache recommended for multi-worker accuracy).

Keys are prefixed with ``hw_metrics:``; use ``get_homework_submit_metrics_snapshot()`` for dashboards.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("classes.metrics")

_PREFIX = "hw_metrics:"


def _incr(key: str, delta: int = 1) -> None:
    try:
        cache.incr(key, delta)
    except ValueError:
        try:
            cache.add(key, delta, timeout=None)
        except Exception:
            logger.debug("metrics incr failed for %s", key, exc_info=True)


def record_homework_submit_attempt() -> None:
    _incr(_PREFIX + "submit_attempt")


def record_homework_submit_success() -> None:
    _incr(_PREFIX + "submit_success")


def record_homework_submit_error() -> None:
    _incr(_PREFIX + "submit_error")


def record_throttle_hit(scope: str) -> None:
    """scope: homework_submit | homework_submit_global | homework_submit_class"""
    _incr(_PREFIX + "throttle_" + scope)


def get_homework_submit_metrics_snapshot() -> dict[str, int | float]:
    """Best-effort counters from cache (missing → 0)."""
    keys = (
        "submit_attempt",
        "submit_success",
        "submit_error",
        "throttle_homework_submit",
        "throttle_homework_submit_global",
        "throttle_homework_submit_class",
    )
    out: dict[str, int | float] = {}
    for k in keys:
        v = cache.get(_PREFIX + k)
        out[k] = int(v) if v is not None else 0
    att = out["submit_attempt"]
    ok = out["submit_success"]
    err = out["submit_error"]
    out["success_rate"] = round(ok / att, 4) if att else 0.0
    out["error_rate"] = round(err / att, 4) if att else 0.0
    out["throttle_hits_total"] = (
        int(out["throttle_homework_submit"])
        + int(out["throttle_homework_submit_global"])
        + int(out["throttle_homework_submit_class"])
    )
    return out


def metrics_require_shared_cache() -> bool:
    return bool(getattr(settings, "CLASSROOM_METRICS_REQUIRE_SHARED_CACHE", True))
