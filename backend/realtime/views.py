from __future__ import annotations

import json
import logging
import time
from collections import deque
from typing import Any

from django.conf import settings
from django.db.models import Case, IntegerField, When
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView


class EventStreamRenderer(BaseRenderer):
    """Renderer used so DRF's content negotiation does not return 406 when a client
    advertises ``Accept: text/event-stream``. The actual streaming response is built
    manually via ``StreamingHttpResponse`` so this renderer is only here to satisfy
    DRF's content-type matching.
    """

    media_type = "text/event-stream"
    format = "txt"
    charset = "utf-8"
    render_style = "text"

    def render(self, data, accepted_media_type=None, renderer_context=None):  # pragma: no cover - never called
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return str(data).encode("utf-8")

from .alerts import evaluate_realtime_thresholds
from .constants import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM
from .load import evaluate_backpressure
from .metrics import get_counter, incr as metric_incr
from .models import RealtimeEvent
from .prometheus import render_prometheus_text
from .redis_bus import channel_user, channel_user_priority, get_redis

logger = logging.getLogger("realtime.sse")


def _sse_pack(*, event_id: int, event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), default=str)
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


def _resync_refresh_hints(classroom_filter: int | None) -> list[str]:
    if classroom_filter is not None:
        return ["stream", "workspace", "comments"]
    return ["stream", "workspace", "comments", "notifications"]


def _redis_channel_bucket(channel_raw: object) -> int:
    ch = channel_raw.decode("utf-8") if isinstance(channel_raw, bytes) else str(channel_raw)
    if ch.endswith(":p:h"):
        return 0
    if ch.endswith(":p:m"):
        return 1
    if ch.endswith(":p:l"):
        return 2
    return 1


def _record_delivery_latency_ms(emit_ts_ms: int | None) -> None:
    if emit_ts_ms is None:
        return
    try:
        now_ms = int(time.time() * 1000)
        lat = now_ms - int(emit_ts_ms)
        if lat < 0 or lat > 86_400_000:
            return
        metric_incr("delivery_latency_ms_total", lat)
        metric_incr("delivery_latency_samples")
    except Exception:
        pass


def _events_queryset(user, last_id: int):
    return (
        RealtimeEvent.objects.filter(user=user, id__gt=last_id)
        .annotate(
            pr_order=Case(
                When(priority=PRIORITY_HIGH, then=0),
                When(priority=PRIORITY_MEDIUM, then=1),
                When(priority=PRIORITY_LOW, then=2),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("pr_order", "id")
    )


class RealtimeEventsSSEView(APIView):
    """
    GET /api/realtime/events/?last_id=<int>&classroom_id=<int>&debug_trace=1

    Hybrid delivery: priority-tiered Redis channels (drain high→medium→low), then DB tail (priority ordered).
    """

    permission_classes = [IsAuthenticated]
    # Accept "text/event-stream" without 406'ing on DRF content negotiation.
    # The actual response is built via StreamingHttpResponse below; this renderer is
    # only here so DRF's negotiator sees a matching renderer for the SSE Accept header.
    from rest_framework.renderers import JSONRenderer as _JSONRenderer
    renderer_classes = [EventStreamRenderer, _JSONRenderer]

    def get(self, request):
        user = request.user
        try:
            last_id = int(request.query_params.get("last_id") or 0)
        except (TypeError, ValueError):
            last_id = 0
        classroom_filter = request.query_params.get("classroom_id")
        try:
            classroom_filter = int(classroom_filter) if classroom_filter else None
        except (TypeError, ValueError):
            classroom_filter = None

        debug_trace = request.query_params.get("debug_trace", "").lower() in ("1", "true", "yes")
        log_trace = debug_trace or getattr(settings, "REALTIME_DEBUG_TRACE", False)

        metric_incr("sse_stream_opens")

        def gen():
            nonlocal last_id
            hello_data: dict[str, Any] = {"ts": timezone.now().isoformat()}
            if debug_trace:
                hello_data["debug_trace"] = True
            yield _sse_pack(event_id=0, event_type="hello", data=hello_data)

            r = get_redis()
            pubsub = None
            if r:
                try:
                    pubsub = r.pubsub(ignore_subscribe_messages=True)
                    chs = [
                        channel_user_priority(user.pk, PRIORITY_HIGH),
                        channel_user_priority(user.pk, PRIORITY_MEDIUM),
                        channel_user_priority(user.pk, PRIORITY_LOW),
                    ]
                    if getattr(settings, "REALTIME_SUBSCRIBE_LEGACY_USER_CHANNEL", False):
                        chs.append(channel_user(user.pk))
                    pubsub.subscribe(*chs)
                except Exception:
                    pubsub = None

            buckets: list[deque[dict[str, Any]]] = [deque(), deque(), deque()]
            last_ping = time.monotonic()
            last_db_poll = 0.0
            stream_start = time.monotonic()
            # End the stream cleanly before the gunicorn worker --timeout fires.
            # A sync worker is parked inside this generator for the whole stream;
            # outliving the timeout gets the worker force-killed (500) and recycled.
            # Returning here completes the response normally (200); the client's
            # EventSource reconnects with last_id, so no events are dropped.
            max_stream_s = float(getattr(settings, "REALTIME_SSE_MAX_STREAM_S", 25))
            try:
                while True:
                    got_event = False

                    if max_stream_s > 0 and (time.monotonic() - stream_start) >= max_stream_s:
                        # Graceful end-of-stream marker, then return to close cleanly.
                        yield _sse_pack(
                            event_id=last_id,
                            event_type="ping",
                            data={"ts": timezone.now().isoformat(), "cycle": True},
                        )
                        metric_incr("sse_stream_cycle")
                        return

                    if pubsub:
                        while True:
                            m = pubsub.get_message(timeout=0)
                            if not m or m.get("type") != "message" or not m.get("data"):
                                break
                            try:
                                data = json.loads(m["data"])
                            except (json.JSONDecodeError, TypeError):
                                continue
                            if not isinstance(data, dict) or int(data.get("user_id", -1)) != user.pk:
                                continue
                            b = _redis_channel_bucket(m.get("channel") or "")
                            buckets[b].append(data)

                        if not any(buckets):
                            m = pubsub.get_message(timeout=0.35)
                            if m and m.get("type") == "message" and m.get("data"):
                                try:
                                    data = json.loads(m["data"])
                                except (json.JSONDecodeError, TypeError):
                                    data = None
                                if isinstance(data, dict) and int(data.get("user_id", -1)) == user.pk:
                                    b = _redis_channel_bucket(m.get("channel") or "")
                                    buckets[b].append(data)

                        for b in (0, 1, 2):
                            while buckets[b]:
                                data = buckets[b].popleft()
                                eid = int(data.get("id", 0))
                                pl = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                                cid = pl.get("classroom_id")
                                emit_ts = data.get("emit_ts_ms")
                                if eid > last_id:
                                    if classroom_filter is not None and cid is not None and int(cid) != int(classroom_filter):
                                        last_id = eid
                                    else:
                                        last_id = eid
                                        if isinstance(emit_ts, int):
                                            _record_delivery_latency_ms(emit_ts)
                                        if log_trace:
                                            logger.info(
                                                "realtime_sse_trace source=redis id=%s type=%s trace_id=%s",
                                                eid,
                                                data.get("event_type"),
                                                pl.get("trace_id") or data.get("trace_id"),
                                            )
                                        yield _sse_pack(
                                            event_id=eid,
                                            event_type=str(data.get("event_type") or "message"),
                                            data=pl,
                                        )
                                        got_event = True
                                        metric_incr("sse_events_from_redis")

                    # DB poll is the expensive part per connection; only do it at a fixed interval.
                    # Redis push will keep the connection hot most of the time.
                    events: list[RealtimeEvent] = []
                    now_m = time.monotonic()
                    db_poll_every = float(getattr(settings, "REALTIME_SSE_DB_POLL_EVERY_S", 0.8))
                    if now_m - last_db_poll >= db_poll_every:
                        last_db_poll = now_m
                        qs = _events_queryset(user, last_id)[:200]
                        events = list(qs)
                    if last_id and len(events) == 200:
                        latest = (
                            RealtimeEvent.objects.filter(user=user).order_by("-id").values_list("id", flat=True).first()
                        )
                        metric_incr("resync_payloads")
                        extra: dict[str, Any] = {
                            "reason": "backlog",
                            "latest_id": int(latest or last_id),
                            "partial_refresh": True,
                            "refresh": _resync_refresh_hints(classroom_filter),
                        }
                        if classroom_filter is not None:
                            extra["classroom_id"] = classroom_filter
                        yield _sse_pack(event_id=last_id, event_type="resync", data=extra)
                        last_id = int(latest or last_id)
                        time.sleep(0.5)
                        continue

                    for e in events:
                        last_id = e.id
                        pl = dict(e.payload or {})
                        pl.setdefault("priority", e.priority)
                        cid = pl.get("classroom_id")
                        if classroom_filter is not None and cid is not None and int(cid) != int(classroom_filter):
                            continue
                        if log_trace:
                            logger.info(
                                "realtime_sse_trace source=db id=%s type=%s trace_id=%s",
                                e.id,
                                e.event_type,
                                pl.get("trace_id"),
                            )
                        yield _sse_pack(event_id=e.id, event_type=e.event_type, data=pl)
                        got_event = True
                        metric_incr("sse_events_from_db")

                    if time.monotonic() - last_ping >= 20:
                        yield _sse_pack(event_id=last_id, event_type="ping", data={"ts": timezone.now().isoformat()})
                        last_ping = time.monotonic()

                    if not got_event and not events:
                        time.sleep(0.15)
            finally:
                if pubsub:
                    try:
                        pubsub.close()
                    except Exception:
                        pass

        resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp


class RealtimeMetricsView(APIView):
    """Operational counters (staff)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        evaluate_realtime_thresholds()
        bp = evaluate_backpressure()

        batches = max(1, get_counter("celery_fanout_batches"))
        total_ms = get_counter("celery_fanout_latency_ms_total")
        lat_n = max(1, get_counter("delivery_latency_samples"))
        lat_sum = get_counter("delivery_latency_ms_total")
        return Response(
            {
                "events_dedupe_suppressed": get_counter("events_dedupe_suppressed"),
                "events_persisted_total": get_counter("events_persisted_total"),
                "events_low_priority_sampled_out": get_counter("events_low_priority_sampled_out"),
                "redis_publish_failures": get_counter("redis_publish_failures"),
                "events_redis_published": get_counter("events_redis_published"),
                "sse_stream_opens": get_counter("sse_stream_opens"),
                "sse_events_from_redis": get_counter("sse_events_from_redis"),
                "sse_events_from_db": get_counter("sse_events_from_db"),
                "resync_payloads": get_counter("resync_payloads"),
                "celery_fanout_batches": get_counter("celery_fanout_batches"),
                "celery_fanout_avg_latency_ms": round(total_ms / batches, 2),
                "delivery_avg_latency_ms": round(lat_sum / lat_n, 2),
                "delivery_latency_samples": get_counter("delivery_latency_samples"),
                "backpressure_level": int(bp.level),
                "backpressure_low_sample_rate": float(bp.low_sample_rate),
                "backpressure_low_dedupe_seconds": int(bp.low_dedupe_seconds),
            }
        )


class RealtimePrometheusMetricsView(APIView):
    """Prometheus text exposition (staff session — put Nginx basic auth or mTLS in front for scraping)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        evaluate_realtime_thresholds()
        body = render_prometheus_text()
        return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
