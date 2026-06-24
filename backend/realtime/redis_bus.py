"""Redis pub/sub for push delivery; DB remains source of replay and durability."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

from .constants import PRIORITY_MEDIUM
from .priority import priority_code

logger = logging.getLogger("realtime.redis")

PublishResult = bool | None  # True ok, False error, None skipped (no REDIS_URL)


def _client():
    url = getattr(settings, "REDIS_URL", None) or ""
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:  # pragma: no cover
        logger.warning("redis_unavailable: %s", e)
        return None


def get_redis():
    """Shared client for SSE pub/sub (same process, one connection per request)."""
    return _client()


def channel_user(user_id: int) -> str:
    """Legacy flat channel (avoid for new publishes; use priority channels)."""
    return f"rt:user:{int(user_id)}"


def channel_user_priority(user_id: int, priority: str) -> str:
    """Tiered channel so SSE can drain high → medium → low without head-of-line blocking."""
    code = priority_code(priority)
    return f"rt:user:{int(user_id)}:p:{code}"


def channel_classroom(classroom_id: int) -> str:
    return f"rt:classroom:{int(classroom_id)}"


def channel_classroom_priority(classroom_id: int, priority: str) -> str:
    code = priority_code(priority)
    return f"rt:classroom:{int(classroom_id)}:p:{code}"


def publish_user_message(*, user_id: int, message: dict[str, Any], priority: str | None = None) -> PublishResult:
    """
    Publish after DB persist. Message must include db id + event_type for SSE lastEventId.
    Returns None if Redis is not configured (not an error — DB replay covers delivery).
    """
    r = _client()
    if not r:
        return None
    try:
        pr = priority or str(message.get("priority") or PRIORITY_MEDIUM)
        ch = channel_user_priority(user_id, pr)
        r.publish(ch, json.dumps(message, separators=(",", ":"), default=str))
        return True
    except Exception as e:  # pragma: no cover
        logger.warning("redis_publish_failed: %s", e)
        return False


def publish_classroom_message(*, classroom_id: int, message: dict[str, Any], priority: str | None = None) -> PublishResult:
    """Classroom-scoped fan-out (optional; for workers / future subscribers)."""
    r = _client()
    if not r:
        return None
    try:
        pr = priority or str(message.get("priority") or PRIORITY_MEDIUM)
        ch = channel_classroom_priority(classroom_id, pr)
        r.publish(ch, json.dumps(message, separators=(",", ":"), default=str))
        return True
    except Exception as e:  # pragma: no cover
        logger.warning("redis_classroom_publish_failed: %s", e)
        return False
