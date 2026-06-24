"""Session stress / correlation flags driven by client telemetry + header checks."""

from __future__ import annotations

import math
import os
import time
from typing import Any

from django.core.cache import cache

from .security_audit import log_security_event
from .security_metrics import incr as security_metric_incr
from .security_metrics import incr_keyed

SESSION_HOLD_KEY = "auth.correl.hold.{uid}"
ROLL_SCORE_KEY = "auth.telemetry.roll.{uid}"
MISMATCH_STREAK_KEY = "auth.correl.ms.{uid}"


def anomaly_roll_threshold() -> float:
    try:
        return max(6.0, float(os.getenv("AUTH_TELEM_ROLL_THRESHOLD", "16")))
    except (TypeError, ValueError):
        return 16.0


def anomaly_release_below() -> float:
    """Rolling score below this clears an active anomaly hold when decay catches up."""
    try:
        return max(3.0, float(os.getenv("AUTH_TELEM_ROLL_RELEASE", "9")))
    except (TypeError, ValueError):
        return 9.0


def decay_lambda_per_hour() -> float:
    """Exponential envelope on the fast rolling anomaly score (~halves roughly every λ hours)."""
    try:
        return max(0.05, float(os.getenv("AUTH_TELEM_DECAY_PER_HOUR", "1.1")))
    except (TypeError, ValueError):
        return 1.1


def decay_lambda_slow_per_hour() -> float:
    """Slower exponential decay for sustained-abuse accumulation (parallel slow score track)."""
    try:
        return max(0.01, float(os.getenv("AUTH_TELEM_SLOW_DECAY_PER_HOUR", "0.12")))
    except (TypeError, ValueError):
        return 0.12


def anomaly_slow_roll_threshold() -> float:
    try:
        return max(anomaly_roll_threshold(), float(os.getenv("AUTH_TELEM_SLOW_THRESHOLD", "42")))
    except (TypeError, ValueError):
        return max(anomaly_roll_threshold(), 42.0)


def anomaly_slow_release_below() -> float:
    try:
        return max(4.0, float(os.getenv("AUTH_TELEM_SLOW_RELEASE", "22")))
    except (TypeError, ValueError):
        return 22.0


def mismatch_streak_deny_threshold() -> int:
    """Only reject mutated requests once enough consecutive mismatches occur."""
    try:
        return max(2, int(os.getenv("AUTH_CORREL_MISMATCH_STREAK_DENY", "6")))
    except (TypeError, ValueError):
        return 6


def corr_recovery_grace_ms() -> int:
    """Ignore ``loss_active`` briefly after SPA reports recovery (React reconciliation slack)."""
    try:
        return max(250, int(os.getenv("AUTH_CORREL_RECOVERY_GRACE_MS", "4200")))
    except (TypeError, ValueError):
        return 4200


def hold_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("AUTH_CORREL_HOLD_TTL_SECONDS", "1800")))
    except (TypeError, ValueError):
        return 1800


def should_block_for_session_hold() -> bool:
    return os.getenv("AUTH_CORREL_BLOCK_ON_HOLD", "").strip() in {"1", "true", "yes"}


def _epoch_ms_maybe(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _read_roll(uid: int) -> tuple[float, float, float]:
    """Fast score, slow score, last_written_ts."""
    now = time.time()
    raw = cache.get(ROLL_SCORE_KEY.format(uid=uid))
    prev_fast = 0.0
    prev_slow = 0.0
    prev_t = now
    if isinstance(raw, dict):
        if "sf" in raw or "ss" in raw:
            prev_fast = float(raw.get("sf") or 0.0)
            prev_slow = float(raw.get("ss") or 0.0)
        else:
            prev_legacy = float(raw.get("s") or 0.0)
            prev_fast = prev_legacy
            prev_slow = prev_legacy
        prev_t = float(raw.get("t") or now)
    return prev_fast, prev_slow, prev_t


def _apply_dual_decay_roll_scores(uid: int) -> tuple[float, float, float]:
    """Decay both tracks from last persisted sample; returns (score_fast, score_slow, now)."""
    prev_fast, prev_slow, prev_t = _read_roll(uid)
    now = time.time()
    dt_h = max(0.0, (now - prev_t) / 3600.0)
    fast_decay = math.exp(-decay_lambda_per_hour() * dt_h)
    slow_decay = math.exp(-decay_lambda_slow_per_hour() * dt_h)
    return prev_fast * fast_decay, prev_slow * slow_decay, now


def _write_roll_dual(uid: int, score_fast: float, score_slow: float, now: float) -> None:
    key = ROLL_SCORE_KEY.format(uid=uid)
    cache.set(
        key,
        {"sf": float(score_fast), "ss": float(score_slow), "t": now},
        timeout=int(os.getenv("AUTH_TELEM_ROLL_CACHE_TTL", "86400") or 86400),
    )


def escalate_on_telemetry_anomaly(request, anomaly_flags: list[str]) -> None:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return
    uid = int(getattr(user, "pk", 0) or 0)
    if uid <= 0:
        return

    score_fast, score_slow, ts = _apply_dual_decay_roll_scores(uid)
    delta = min(26.0, 1.35 + float(len(anomaly_flags or [])) * 1.95)
    score_fast += delta
    score_slow += delta

    rolled = incr_keyed(
        "auth_telemetry_anomaly_batches",
        str(uid),
        1,
        ttl_seconds=int(os.getenv("AUTH_TELEM_BATCH_COUNT_TTL", "7200") or 7200),
    )

    security_metric_incr("auth_telemetry_anomaly_user_escalations_total")
    log_security_event(
        user_id=uid,
        event_type="auth_telemetry_anomaly_batch",
        request=request,
        detail={
            "flags": anomaly_flags,
            "rolling_score_fast": score_fast,
            "rolling_score_slow": score_slow,
            "batch_index": rolled,
        },
        severity="warning",
    )

    _write_roll_dual(uid, score_fast, score_slow, ts)

    rl_fast = anomaly_roll_threshold()
    rl_slow = anomaly_slow_roll_threshold()
    over_fast_threshold = score_fast >= rl_fast
    over_slow_threshold = score_slow >= rl_slow

    below_fast_rel = score_fast <= anomaly_release_below()
    below_slow_rel = score_slow <= anomaly_slow_release_below()
    release_hold = below_fast_rel and below_slow_rel

    if over_fast_threshold or over_slow_threshold:
        cache.set(
            SESSION_HOLD_KEY.format(uid=uid),
            {
                "at": time.time(),
                "flags": anomaly_flags,
                "score_fast": score_fast,
                "score_slow": score_slow,
            },
            timeout=hold_ttl_seconds(),
        )
        security_metric_incr("auth_correl_session_hold_set_total")
    elif release_hold:
        cache.delete(SESSION_HOLD_KEY.format(uid=int(uid)))


def active_session_hold(uid: int) -> dict[str, Any] | None:
    try:
        raw = cache.get(SESSION_HOLD_KEY.format(uid=int(uid)))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def clear_session_hold(uid: int) -> None:
    try:
        cache.delete(SESSION_HOLD_KEY.format(uid=int(uid)))
    except Exception:
        return


def record_correl_header_mismatch(
    request,
    *,
    issues: list[str],
) -> None:
    """Header / session inconsistency (SPA desync, proxy issues, abuse)."""
    security_metric_incr("auth_correl_header_mismatch_events_total")
    uid = None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        uid = int(getattr(user, "pk", 0) or 0)
    log_security_event(
        user_id=uid,
        event_type="auth_correl_header_mismatch",
        request=request,
        detail={"issues": issues[:12]},
        severity="warning",
    )
    if uid and uid > 0:
        incr_keyed(
            "auth_correl_header_mismatch_user",
            str(uid),
            1,
            ttl_seconds=3600,
        )


def correlate_mismatch_bump(uid: int) -> int:
    """Consecutive SPA↔cookie mismatch streak (TTL’d)."""
    key = MISMATCH_STREAK_KEY.format(uid=int(uid))
    try:
        n = int(cache.get(key) or 0) + 1
    except (TypeError, ValueError):
        n = 1
    n = min(int(n), 64)
    try:
        cache.set(key, n, timeout=7200)
    except Exception:
        pass
    return n


def correlate_mismatch_relax(uid: int) -> int:
    """Successful healthy-ish request halves the mismatch streak rapidly."""
    key = MISMATCH_STREAK_KEY.format(uid=int(uid))
    try:
        n = max(0, int(cache.get(key) or 0) - 3)
        cache.set(key, n, timeout=7200)
        return int(n)
    except Exception:
        return 0
