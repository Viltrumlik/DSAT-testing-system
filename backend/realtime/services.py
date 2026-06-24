from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Max
from django.utils import timezone

from classes.models import ClassroomMembership

from .constants import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM
from .load import evaluate_backpressure, should_emit
from .metrics import incr as metric_incr
from .models import RealtimeEvent
from .redis_bus import publish_classroom_message, publish_user_message

User = get_user_model()
logger = logging.getLogger("realtime.emit")

# Event types that always bypass the dedupe window (distinct logical events).
_BYPASS_DEDUPE_PREFIXES: tuple[str, ...] = ("grade.",)


def _attach_refresh_hints(event_type: str, payload: dict) -> dict:
    out = dict(payload)
    refresh: list[str] = []
    if event_type == "stream.updated":
        refresh.append("stream")
    if event_type == "workspace.updated":
        refresh.append("workspace")
    if event_type == "comments.updated":
        refresh.append("comments")
    if event_type == "notifications.updated":
        refresh.append("notifications")
    if refresh:
        out["refresh"] = refresh
    return out


def classify_event(event_type: str, payload: dict | None) -> tuple[str, bool]:
    """
    Returns (priority, apply_dedupe_window).
    High priority is never suppressed by the dedupe window.
    """
    p = dict(payload or {})
    explicit = p.get("priority")
    if explicit in (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW):
        pr = str(explicit)
        return pr, pr != PRIORITY_HIGH

    if any(event_type.startswith(pref) for pref in _BYPASS_DEDUPE_PREFIXES):
        return PRIORITY_HIGH, False

    reason = (p.get("reason") or "").lower()

    if event_type == "notifications.updated" and reason in ("graded", "grade"):
        return PRIORITY_HIGH, False
    if event_type == "workspace.updated" and reason in ("grade", "graded"):
        return PRIORITY_HIGH, False
    if event_type == "stream.updated" and reason == "grade":
        return PRIORITY_HIGH, False
    if reason in ("assignment_created", "assignment_create"):
        return PRIORITY_HIGH, False

    if reason in ("submission", "submitted"):
        return PRIORITY_MEDIUM, True
    if event_type == "workspace.updated" and reason == "submission":
        return PRIORITY_MEDIUM, True

    if event_type == "comments.updated":
        return PRIORITY_LOW, True
    if reason in ("comment", "comment_reply", "post", "announcement"):
        return PRIORITY_LOW, True

    return PRIORITY_MEDIUM, True


def _dedupe_key(*, user_id: int, event_type: str, payload: dict, apply_dedupe: bool) -> str:
    if not apply_dedupe:
        return ""
    p = payload or {}
    core = {
        "u": int(user_id),
        "t": str(event_type),
        "c": p.get("classroom_id"),
        "tt": p.get("target_type"),
        "tid": p.get("target_id"),
        "reason": p.get("reason"),
        "comment_id": p.get("comment_id"),
        "parent_id": p.get("parent_id"),
        "submission_id": p.get("submission_id"),
        "assignment_id": p.get("assignment_id"),
        "item_id": p.get("item_id"),
        "notification_id": p.get("notification_id"),
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:64]


def _normalize_emit_row(*, user_id: int, event_type: str, payload: dict | None) -> dict:
    p = _attach_refresh_hints(str(event_type), dict(payload or {}))
    priority, apply_dedupe = classify_event(str(event_type), p)
    p["priority"] = priority
    dk = _dedupe_key(user_id=int(user_id), event_type=str(event_type), payload=p, apply_dedupe=apply_dedupe)
    return {
        "user_id": int(user_id),
        "event_type": str(event_type),
        "payload": p,
        "dedupe_key": dk,
        "priority": priority,
    }


def _queue_available() -> bool:
    try:
        return bool(getattr(settings, "CELERY_BROKER_URL", None))
    except Exception:
        return False


def _enqueue(rows: list[dict]) -> None:
    try:
        from .tasks import fanout_realtime_events

        fanout_realtime_events.delay(rows)
        return
    except Exception:
        persist_realtime_batch(rows)


def _publish_row(obj: RealtimeEvent) -> None:
    if not obj.pk:
        return
    emit_ts_ms = int(time.time() * 1000)
    pl = obj.payload or {}
    msg = {
        "id": int(obj.pk),
        "user_id": int(obj.user_id),
        "event_type": str(obj.event_type),
        "payload": pl,
        "priority": str(obj.priority),
        "emit_ts_ms": emit_ts_ms,
    }
    tid = pl.get("trace_id")
    if tid:
        msg["trace_id"] = tid
    ok = publish_user_message(user_id=obj.user_id, message=msg, priority=str(obj.priority))
    if ok is True:
        metric_incr("events_redis_published")
    elif ok is False:
        metric_incr("redis_publish_failures")
    cid = pl.get("classroom_id")
    if cid is not None:
        publish_classroom_message(classroom_id=int(cid), message=msg, priority=str(obj.priority))


def persist_realtime_batch(rows: list[dict], *, dedupe_window_seconds: int | None = None) -> tuple[int, int]:
    """
    Shared durable write + Redis fan-out. Returns (inserted_count, dedupe_suppressed_count).
    """
    if not rows:
        return 0, 0
    default_s = int(dedupe_window_seconds or getattr(settings, "REALTIME_DEFAULT_DEDUPE_SECONDS", 2))
    low_s = int(getattr(settings, "REALTIME_LOW_PRIORITY_DEDUPE_SECONDS", 5))
    low_sample = float(getattr(settings, "REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE", 1.0))
    low_sample = max(0.0, min(1.0, low_sample))

    # Self-regulating: adjust low-only parameters under pressure.
    bp = evaluate_backpressure()
    metric_incr("backpressure_level", int(bp.level))
    low_s = max(low_s, int(bp.low_dedupe_seconds))
    low_sample = min(low_sample, float(bp.low_sample_rate))

    now = timezone.now()
    max_win = max(default_s, low_s)
    cutoff_global = now - timedelta(seconds=max_win)

    by_user: dict[int, list[dict]] = {}
    for r in rows:
        uid = int(r["user_id"])
        by_user.setdefault(uid, []).append(r)

    suppressed = 0
    to_insert: list[RealtimeEvent] = []
    for uid, user_rows in by_user.items():
        keys_set = {r["dedupe_key"] for r in user_rows if r.get("dedupe_key")}
        latest_per_key: dict[str, object] = {}
        if keys_set:
            latest_per_key = dict(
                RealtimeEvent.objects.filter(
                    user_id=uid, dedupe_key__in=keys_set, created_at__gte=cutoff_global
                )
                .values("dedupe_key")
                .annotate(m=Max("created_at"))
                .values_list("dedupe_key", "m")
            )

        batch_seen: set[str] = set()
        for r in user_rows:
            pr = str(r.get("priority") or PRIORITY_MEDIUM)
            if not should_emit(priority=pr, event_type=str(r.get("event_type") or "")):
                metric_incr("events_dropped_by_backpressure")
                continue
            if pr == PRIORITY_LOW and low_sample < 1.0 and random.random() > low_sample:
                metric_incr("events_low_priority_sampled_out")
                continue

            k = r.get("dedupe_key") or ""
            if not k:
                to_insert.append(
                    RealtimeEvent(
                        user_id=uid,
                        event_type=str(r["event_type"]),
                        payload=r.get("payload") or {},
                        dedupe_key="",
                        priority=pr,
                    )
                )
                continue

            if k in batch_seen:
                suppressed += 1
                metric_incr("events_dedupe_suppressed")
                continue

            win = low_s if pr == PRIORITY_LOW else default_s
            cutoff_r = now - timedelta(seconds=win)
            last_ts = latest_per_key.get(k)
            if last_ts is not None and last_ts >= cutoff_r:
                suppressed += 1
                metric_incr("events_dedupe_suppressed")
                continue

            to_insert.append(
                RealtimeEvent(
                    user_id=uid,
                    event_type=str(r["event_type"]),
                    payload=r.get("payload") or {},
                    dedupe_key=k,
                    priority=pr,
                )
            )
            batch_seen.add(k)

    if not to_insert:
        return 0, suppressed

    RealtimeEvent.objects.bulk_create(to_insert, batch_size=int(getattr(settings, "REALTIME_BULK_BATCH_SIZE", 500)))
    metric_incr("events_persisted_total", len(to_insert))

    for obj in to_insert:
        if obj.pk:
            _publish_row(obj)
        else:
            metric_incr("events_missing_pk_after_insert")
            logger.warning("realtime_missing_pk_after_insert user=%s type=%s", obj.user_id, obj.event_type)

    logger.info("realtime_events_written n=%s suppressed=%s users=%s", len(to_insert), suppressed, len(by_user))
    return len(to_insert), suppressed


def emit_to_user(*, user_id: int, event_type: str, payload: dict) -> None:
    rows = [_normalize_emit_row(user_id=int(user_id), event_type=str(event_type), payload=payload or {})]
    if _queue_available():
        _enqueue(rows)
    else:
        persist_realtime_batch(rows)


def emit_to_users(*, user_ids: Iterable[int], event_type: str, payload: dict) -> None:
    p = payload or {}
    uids = {int(x) for x in user_ids if x}
    rows = [_normalize_emit_row(user_id=uid, event_type=str(event_type), payload=p) for uid in uids]
    if not rows:
        return
    if _queue_available():
        _enqueue(rows)
    else:
        persist_realtime_batch(rows)


def emit_to_classroom_members(
    *,
    classroom_id: int,
    event_type: str,
    payload: dict,
    roles: tuple[str, ...] | None = None,
) -> None:
    qs = ClassroomMembership.objects.filter(classroom_id=classroom_id)
    if roles:
        qs = qs.filter(role__in=roles)
    user_ids = list(qs.values_list("user_id", flat=True))
    emit_to_users(user_ids=user_ids, event_type=event_type, payload=payload or {})
