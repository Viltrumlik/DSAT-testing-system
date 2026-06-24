from __future__ import annotations

import time
from typing import Any

# Aligned with frontend `AuthLossReason` and event kinds.
LOSS_REASONS = frozenset({"EXPIRED", "NETWORK", "SERVER", "NO_SESSION"})
EVENT_KINDS = frozenset({"loss", "refresh", "cancel", "guard_peak"})

# Same caps as the SPA (queue + one batch).
MAX_EVENTS_PER_BATCH = 300
MAX_SNAPSHOT_LOSS_PER_REASON = 10_000
MAX_NUMERIC = 1_000_000_000


def _is_intish(x: Any) -> bool:
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float) and x.is_integer():
        return True
    return False


def validate_client_auth_telemetry_body(body: dict[str, Any]) -> tuple[bool, str]:
    if body.get("schema") != 1:
        return False, "invalid_schema"

    ct = body.get("client_ts")
    if not _is_intish(ct):
        return False, "invalid_client_ts"
    now_ms = int(time.time() * 1000)
    if abs(int(ct) - now_ms) > 7 * 24 * 3600 * 1000:
        return False, "client_ts_out_of_range"

    events = body.get("events")
    if not isinstance(events, list):
        return False, "events_not_list"
    if len(events) > MAX_EVENTS_PER_BATCH:
        return False, "events_too_many"

    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            return False, f"event_{i}_not_object"
        k = ev.get("k")
        if k not in EVENT_KINDS:
            return False, f"event_{i}_invalid_k"
        t = ev.get("t")
        if not _is_intish(t) or int(t) < 0 or int(t) > now_ms + 3600_000:
            return False, f"event_{i}_invalid_t"
        if k == "loss":
            r = ev.get("reason")
            if not isinstance(r, str) or r not in LOSS_REASONS:
                return False, f"event_{i}_invalid_reason"
        elif k == "guard_peak":
            d = ev.get("depth")
            if not _is_intish(d) or int(d) < 0 or int(d) > 32:
                return False, f"event_{i}_invalid_guard_depth"

    correl = body.get("correl")
    if correl is not None:
        if not isinstance(correl, dict):
            return False, "correl_not_object"
        allowed_correl = frozenset(
            {
                "auth_boot",
                "auth_loss_version",
                "auth_recovery_version",
                "auth_loss_reason",
                "me_guard_depth",
                "me_guard_depth_max",
                "last_auth_loss_at",
                "last_auth_recovery_at",
            }
        )
        if set(correl.keys()) - allowed_correl:
            return False, "correl_extra_keys"
        g = correl.get("me_guard_depth")
        if g is not None and (not _is_intish(g) or int(g) < 0 or int(g) > 32):
            return False, "correl_guard_depth"
        gmx_corr = correl.get("me_guard_depth_max")
        if gmx_corr is not None and (not _is_intish(gmx_corr) or int(gmx_corr) < 0 or int(gmx_corr) > 32):
            return False, "correl_guard_depth_max"
        v = correl.get("auth_loss_version")
        if v is not None and (not _is_intish(v) or int(v) < 0 or int(v) > MAX_NUMERIC):
            return False, "correl_loss_version"
        rv = correl.get("auth_recovery_version")
        if rv is not None and (not _is_intish(rv) or int(rv) < 0 or int(rv) > MAX_NUMERIC):
            return False, "correl_recovery_version"
        la = correl.get("last_auth_loss_at")
        if la is not None:
            if not _is_intish(la):
                return False, "correl_last_loss_ts"
            if abs(int(la) - now_ms) > 30 * 24 * 3600 * 1000:
                return False, "correl_last_loss_ts_range"
        lra = correl.get("last_auth_recovery_at")
        if lra is not None:
            if not _is_intish(lra):
                return False, "correl_last_recovery_ts"
            if abs(int(lra) - now_ms) > 30 * 24 * 3600 * 1000:
                return False, "correl_last_recovery_ts_range"
        ar = correl.get("auth_loss_reason")
        if ar is not None and (not isinstance(ar, str) or ar not in LOSS_REASONS):
            return False, "correl_loss_reason"
        ab = correl.get("auth_boot")
        if ab is not None and (not isinstance(ab, str) or len(ab) > 64):
            return False, "correl_auth_boot"

    snap = body.get("snapshot")
    if snap is not None:
        if not isinstance(snap, dict):
            return False, "snapshot_not_object"
        alt = snap.get("auth_loss_total")
        if alt is not None:
            if not isinstance(alt, dict):
                return False, "snapshot_loss_total"
            for kr, vr in alt.items():
                if kr not in LOSS_REASONS:
                    return False, "snapshot_loss_key"
                if not _is_intish(vr) or int(vr) < 0 or int(vr) > MAX_SNAPSHOT_LOSS_PER_REASON:
                    return False, "snapshot_loss_value"
        for key in ("auth_refresh_total", "auth_cancel_total"):
            v2 = snap.get(key)
            if v2 is not None and (not _is_intish(v2) or int(v2) < 0 or int(v2) > MAX_SNAPSHOT_LOSS_PER_REASON):
                return False, f"snapshot_{key}"
        gmx = snap.get("me_guard_depth_max")
        if gmx is not None and (not _is_intish(gmx) or int(gmx) < 0 or int(gmx) > 32):
            return False, "snapshot_guard_depth_max"
        dla = snap.get("last_auth_loss_at")
        if dla is not None and (not _is_intish(dla) or int(dla) < 0):
            return False, "snapshot_last_loss_at"
        dra = snap.get("last_auth_recovery_at")
        if dra is not None and (not _is_intish(dra) or int(dra) < 0):
            return False, "snapshot_last_recovery_at"

    return True, ""


def score_telemetry_anomalies(
    body: dict[str, Any], events_len: int, client_ts: int, now_ms: int
) -> list[str]:
    """
    Heuristics for log-level anomaly flags (not blocking).
    """
    flags: list[str] = []
    if events_len > 200:
        flags.append("large_event_batch")
    if events_len > 0 and client_ts < now_ms - 6 * 3600 * 1000:
        flags.append("stale_client_timeline")

    snap = body.get("snapshot")
    if isinstance(snap, dict):
        alt = snap.get("auth_loss_total")
        if isinstance(alt, dict):
            for _k, v in alt.items():
                try:
                    if int(v) > 5_000:
                        flags.append("extreme_loss_counters")
                        break
                except (TypeError, ValueError):
                    flags.append("corrupt_loss_counters")
                    break
        for key in ("auth_refresh_total", "auth_cancel_total"):
            v2 = snap.get(key)
            try:
                if v2 is not None and int(v2) > 50_000:
                    flags.append("extreme_refresh_or_cancel")
                    break
            except (TypeError, ValueError):
                flags.append("corrupt_refresh_cancel")
                break

    correl = body.get("correl")
    if isinstance(correl, dict):
        g = correl.get("me_guard_depth")
        try:
            if g is not None and int(g) > 8:
                flags.append("implausible_guard_depth")
        except (TypeError, ValueError):
            flags.append("corrupt_guard_depth")

    events = body.get("events")
    if isinstance(events, list):
        guard_peaks = sum(1 for ev in events if isinstance(ev, dict) and ev.get("k") == "guard_peak")
        if guard_peaks > 12:
            flags.append("guard_peak_storm")

    return flags
