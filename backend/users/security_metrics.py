from __future__ import annotations

from django.core.cache import cache


PREFIX = "users.security.metric."


def incr(name: str, n: int = 1) -> None:
    try:
        cache_key = f"{PREFIX}{name}"
        cache.incr(cache_key, n)
    except ValueError:
        cache.set(f"{PREFIX}{name}", int(n), timeout=None)
    except Exception:
        return


def get(name: str) -> int:
    try:
        v = cache.get(f"{PREFIX}{name}")
        return int(v or 0)
    except Exception:
        return 0


def incr_keyed(prefix: str, key: str, n: int = 1, *, ttl_seconds: int) -> int:
    """
    Increment a keyed counter with TTL and return the new value.
    Used for rate-based detection (per-user per hour, etc).
    """
    cache_key = f"{PREFIX}{prefix}.{key}"
    try:
        v = cache.incr(cache_key, n)
        return int(v)
    except ValueError:
        cache.set(cache_key, int(n), timeout=int(ttl_seconds))
        return int(n)
    except Exception:
        return 0


def get_keyed(prefix: str, key: str) -> int:
    try:
        v = cache.get(f"{PREFIX}{prefix}.{key}")
        return int(v or 0)
    except Exception:
        return 0

