"""
Backpressure / load estimation for realtime.

Design goals:
- Cheap: O(1) per emission; no DB reads.
- Shared: state stored in Django cache (use Redis cache in production).
- Conservative: never impacts high-priority events.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from .constants import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM
from .metrics import get_counter


@dataclass(frozen=True)
class LoadSnapshot:
    ts: float
    events_persisted: int
    dedupe_suppressed: int
    resync_payloads: int
    redis_failures: int
    redis_published: int
    delivery_latency_sum_ms: int
    delivery_latency_samples: int


@dataclass(frozen=True)
class LoadRates:
    dt_s: float
    persisted_per_s: float
    suppressed_per_s: float
    resync_per_s: float
    redis_fail_per_s: float
    redis_fail_ratio: float
    delivery_avg_latency_ms: float


@dataclass(frozen=True)
class BackpressureDecision:
    level: int  # 0..3
    low_sample_rate: float  # 0..1
    low_dedupe_seconds: int
    drop_low: bool
    drop_medium: bool


_SNAPSHOT_KEY = "rt:load:snapshot:v1"
_DECISION_KEY = "rt:load:decision:v1"


def _now() -> float:
    return time.monotonic()


def _read_snapshot() -> LoadSnapshot | None:
    return cache.get(_SNAPSHOT_KEY)


def _write_snapshot(s: LoadSnapshot) -> None:
    cache.set(_SNAPSHOT_KEY, s, timeout=180)


def _write_decision(d: BackpressureDecision) -> None:
    cache.set(_DECISION_KEY, d, timeout=30)


def get_cached_decision() -> BackpressureDecision | None:
    return cache.get(_DECISION_KEY)


def _make_snapshot() -> LoadSnapshot:
    return LoadSnapshot(
        ts=_now(),
        events_persisted=get_counter("events_persisted_total"),
        dedupe_suppressed=get_counter("events_dedupe_suppressed"),
        resync_payloads=get_counter("resync_payloads"),
        redis_failures=get_counter("redis_publish_failures"),
        redis_published=get_counter("events_redis_published"),
        delivery_latency_sum_ms=get_counter("delivery_latency_ms_total"),
        delivery_latency_samples=get_counter("delivery_latency_samples"),
    )


def _rates(prev: LoadSnapshot, cur: LoadSnapshot) -> LoadRates:
    dt = max(0.001, cur.ts - prev.ts)
    persisted = max(0, cur.events_persisted - prev.events_persisted) / dt
    suppressed = max(0, cur.dedupe_suppressed - prev.dedupe_suppressed) / dt
    resync = max(0, cur.resync_payloads - prev.resync_payloads) / dt
    redis_fail = max(0, cur.redis_failures - prev.redis_failures) / dt

    redis_pub = max(0, cur.redis_published - prev.redis_published)
    redis_fail_cnt = max(0, cur.redis_failures - prev.redis_failures)
    redis_fail_ratio = redis_fail_cnt / max(1, redis_pub + redis_fail_cnt)

    lat_samples = max(0, cur.delivery_latency_samples - prev.delivery_latency_samples)
    lat_sum = max(0, cur.delivery_latency_sum_ms - prev.delivery_latency_sum_ms)
    avg_lat = (lat_sum / lat_samples) if lat_samples else 0.0

    return LoadRates(
        dt_s=dt,
        persisted_per_s=persisted,
        suppressed_per_s=suppressed,
        resync_per_s=resync,
        redis_fail_per_s=redis_fail,
        redis_fail_ratio=redis_fail_ratio,
        delivery_avg_latency_ms=avg_lat,
    )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def evaluate_backpressure(*, force_refresh: bool = False) -> BackpressureDecision:
    """
    Computes and caches a decision.

    Level interpretation:
    - 0: normal
    - 1: elevated
    - 2: high
    - 3: critical (aggressive low sampling + longer low dedupe; optional low drops)
    """
    if not bool(getattr(settings, "REALTIME_BACKPRESSURE_ENABLED", True)):
        d = BackpressureDecision(level=0, low_sample_rate=1.0, low_dedupe_seconds=int(getattr(settings, "REALTIME_LOW_PRIORITY_DEDUPE_SECONDS", 5)), drop_low=False, drop_medium=False)
        _write_decision(d)
        return d

    if not force_refresh:
        cached = get_cached_decision()
        if cached is not None:
            return cached

    cur = _make_snapshot()
    prev = _read_snapshot()
    if prev is None:
        _write_snapshot(cur)
        d0 = BackpressureDecision(
            level=0,
            low_sample_rate=float(getattr(settings, "REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE", 1.0)),
            low_dedupe_seconds=int(getattr(settings, "REALTIME_LOW_PRIORITY_DEDUPE_SECONDS", 5)),
            drop_low=False,
            drop_medium=False,
        )
        _write_decision(d0)
        return d0

    r = _rates(prev, cur)
    _write_snapshot(cur)

    # Score is intentionally simple and monotonic; tune via env vars.
    # Persistent event rate thresholds (per second).
    t_elev = float(getattr(settings, "REALTIME_BP_PERSISTED_PER_S_ELEVATED", 80))
    t_high = float(getattr(settings, "REALTIME_BP_PERSISTED_PER_S_HIGH", 160))
    t_crit = float(getattr(settings, "REALTIME_BP_PERSISTED_PER_S_CRITICAL", 260))

    # Delivery latency thresholds (ms).
    t_lat_elev = float(getattr(settings, "REALTIME_BP_LATENCY_MS_ELEVATED", 250))
    t_lat_high = float(getattr(settings, "REALTIME_BP_LATENCY_MS_HIGH", 600))
    t_lat_crit = float(getattr(settings, "REALTIME_BP_LATENCY_MS_CRITICAL", 1200))

    # Resync rate thresholds (per second).
    t_resync_elev = float(getattr(settings, "REALTIME_BP_RESYNC_PER_S_ELEVATED", 0.2))
    t_resync_high = float(getattr(settings, "REALTIME_BP_RESYNC_PER_S_HIGH", 0.6))
    t_resync_crit = float(getattr(settings, "REALTIME_BP_RESYNC_PER_S_CRITICAL", 1.2))

    # Redis failure ratio thresholds.
    t_rf_elev = float(getattr(settings, "REALTIME_BP_REDIS_FAIL_RATIO_ELEVATED", 0.02))
    t_rf_high = float(getattr(settings, "REALTIME_BP_REDIS_FAIL_RATIO_HIGH", 0.05))
    t_rf_crit = float(getattr(settings, "REALTIME_BP_REDIS_FAIL_RATIO_CRITICAL", 0.12))

    level = 0
    if r.persisted_per_s >= t_elev or r.delivery_avg_latency_ms >= t_lat_elev or r.resync_per_s >= t_resync_elev or r.redis_fail_ratio >= t_rf_elev:
        level = 1
    if r.persisted_per_s >= t_high or r.delivery_avg_latency_ms >= t_lat_high or r.resync_per_s >= t_resync_high or r.redis_fail_ratio >= t_rf_high:
        level = 2
    if r.persisted_per_s >= t_crit or r.delivery_avg_latency_ms >= t_lat_crit or r.resync_per_s >= t_resync_crit or r.redis_fail_ratio >= t_rf_crit:
        level = 3

    base_sample = float(getattr(settings, "REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE", 1.0))
    base_low_dedupe = int(getattr(settings, "REALTIME_LOW_PRIORITY_DEDUPE_SECONDS", 5))
    max_low_dedupe = int(getattr(settings, "REALTIME_BP_MAX_LOW_DEDUPE_SECONDS", 20))
    min_sample = float(getattr(settings, "REALTIME_BP_MIN_LOW_SAMPLE_RATE", 0.05))

    # Decision: progressively more aggressive on low-only.
    # level 0: keep configured sampling/dedupe
    # level 1: reduce sample by ~15%, increase low dedupe by +2s
    # level 2: reduce sample by ~40%, increase low dedupe by +6s
    # level 3: reduce sample by ~70% (floor), increase low dedupe by +12s, allow dropping low from DB replay importance (sampling already does it)
    sample_mult = {0: 1.0, 1: 0.85, 2: 0.6, 3: 0.3}[level]
    low_sample = _clamp(base_sample * sample_mult, min_sample, 1.0)
    low_dedupe = min(max_low_dedupe, base_low_dedupe + {0: 0, 1: 2, 2: 6, 3: 12}[level])

    drop_low = bool(getattr(settings, "REALTIME_BP_DROP_LOW_AT_CRITICAL", True)) and level >= 3
    drop_medium = bool(getattr(settings, "REALTIME_BP_DROP_MEDIUM_AT_CRITICAL", False)) and level >= 3

    d = BackpressureDecision(
        level=level,
        low_sample_rate=low_sample,
        low_dedupe_seconds=int(low_dedupe),
        drop_low=drop_low,
        drop_medium=drop_medium,
    )
    _write_decision(d)
    return d


def should_emit(*, priority: str, event_type: str) -> bool:
    """
    Producer throttling: high is always allowed.
    Medium/low can be dropped under critical load depending on config.
    """
    if str(priority) == PRIORITY_HIGH:
        return True
    d = get_cached_decision() or evaluate_backpressure()
    if d.level < 3:
        return True
    if str(priority) == PRIORITY_LOW and d.drop_low:
        return False
    if str(priority) == PRIORITY_MEDIUM and d.drop_medium:
        return False
    return True

