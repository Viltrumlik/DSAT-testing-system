from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from django.core.cache import cache


def get_redis_health_snapshot(*, timeout_s: float = 0.5) -> dict[str, Any]:
    """
    Best-effort Redis health probe for:
    - sliding-window ZSET counters (REDIS_URL)
    - default cache backend (CACHES['default'])
    """
    cache_backend = str(getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "") or "")
    degraded_sliding = bool(cache.get("assess:degraded:redis_sliding"))

    url = str(getattr(settings, "REDIS_URL", "") or "").strip()
    if not url or not url.lower().startswith("redis"):
        return {
            "enabled": False,
            "ok": False,
            "reason": "no_redis_url",
            "cache_backend": cache_backend,
            "sliding_degraded": degraded_sliding,
            "latency_ms": None,
        }

    try:
        import redis

        r = redis.Redis.from_url(url, socket_connect_timeout=timeout_s, socket_timeout=timeout_s)
        t0 = time.perf_counter()
        r.ping()
        ms = (time.perf_counter() - t0) * 1000.0
        return {
            "enabled": True,
            "ok": True,
            "reason": None,
            "cache_backend": cache_backend,
            "sliding_degraded": degraded_sliding,
            "latency_ms": round(ms, 2),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "reason": f"{exc.__class__.__name__}",
            "cache_backend": cache_backend,
            "sliding_degraded": True,
            "latency_ms": None,
        }

