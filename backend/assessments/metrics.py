"""Lightweight counters for assessment/homework monitoring (use Redis/shared cache in prod)."""

from __future__ import annotations

from django.core.cache import cache

from core.drills import env_flag

PREFIX = "as:metrics:"


def incr(key: str, delta: int = 1) -> int:
    if env_flag("DRILL_REDIS_DOWN"):
        raise ConnectionError("DRILL_REDIS_DOWN")
    try:
        return int(cache.incr(PREFIX + key, delta))
    except ValueError:
        cache.set(PREFIX + key, delta, timeout=None)
        return delta


def get_counter(key: str) -> int:
    if env_flag("DRILL_REDIS_DOWN"):
        raise ConnectionError("DRILL_REDIS_DOWN")
    v = cache.get(PREFIX + key)
    return int(v) if v is not None else 0

