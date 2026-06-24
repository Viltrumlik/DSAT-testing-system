from __future__ import annotations

"""
Core metrics facade.

Adapter-first: delegate to existing `exams.metrics` implementation (cache-backed counters).
In later refactors, domains should call `core.metrics.*` and not import per-domain metrics modules.
"""

from access.services import normalized_role
from exams.metrics import get_counter as _raw_get_counter
from exams.metrics import incr as _raw_incr


def incr(key: str, delta: int = 1) -> int:
    """
    Best-effort counter increment.
    Never break production flows if the metrics backend is down (e.g. Redis outage).
    """
    try:
        return int(_raw_incr(key, delta))
    except Exception:
        return 0


def get_counter(key: str) -> int:
    try:
        return int(_raw_get_counter(key))
    except Exception:
        return 0


def _role_suffix(role: str | None) -> str:
    r = (role or "").strip().lower()
    if not r:
        r = "unknown"
    r = "".join(ch for ch in r if ch.isalnum() or ch in ("_", "-"))[:32]
    return r or "unknown"


def incr_role(key: str, *, actor) -> int:
    """
    Per-role telemetry without Prometheus label support (suffix-based).
    """
    try:
        role = normalized_role(actor)
    except Exception:
        role = None
    return incr(f"{key}_role_{_role_suffix(role)}", 1)

__all__ = ["incr", "get_counter", "incr_role"]

