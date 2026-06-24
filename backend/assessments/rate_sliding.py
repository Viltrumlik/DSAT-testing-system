from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from django.conf import settings

logger = logging.getLogger("assessments.rate_sliding")


def _redis_url() -> str:
    return str(getattr(settings, "REDIS_URL", "") or "").strip()


def sliding_window_increment_and_count(*, key: str, window_seconds: int) -> tuple[int, bool]:
    """
    True sliding-window counter using Redis sorted sets (when REDIS_URL is set).

    Returns (count_after_this_event, used_redis_sliding).
    """
    window_seconds = max(1, min(86400, int(window_seconds)))
    url = _redis_url()
    if not url or not url.lower().startswith("redis"):
        return 0, False

    try:
        import redis

        r = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
        now = time.time()
        cutoff = now - float(window_seconds)
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        max_events = int(getattr(settings, "ASSESSMENT_SW_ZSET_MAX_EVENTS", 5000) or 5000)
        max_events = max(100, min(200_000, max_events))
        pipe = r.pipeline()
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, 0, cutoff)
        # Memory protection: cap cardinality even if time-based trimming is delayed.
        pipe.zremrangebyrank(key, 0, -(max_events + 1))
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 60)
        _, _, count, _ = pipe.execute()
        return int(count), True
    except Exception:
        logger.exception("sliding_window_increment_and_count failed key=%s", key)
        # Mark degradation so ops metrics can surface it (best-effort; cache may be local).
        try:
            from django.core.cache import cache

            cache.set("assess:degraded:redis_sliding", True, timeout=60)
        except Exception:
            pass
        return 0, False
