"""Lightweight counters for monitoring (use Redis or shared cache in prod)."""

from __future__ import annotations

from django.core.cache import cache

PREFIX = "rt:metrics:"


def incr(key: str, delta: int = 1) -> int:
    try:
        return int(cache.incr(PREFIX + key, delta))
    except ValueError:
        cache.set(PREFIX + key, delta, timeout=None)
        return delta


def get_counter(key: str) -> int:
    v = cache.get(PREFIX + key)
    return int(v) if v is not None else 0
