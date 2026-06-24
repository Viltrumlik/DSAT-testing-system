"""Prometheus text exposition for realtime counters (no extra dependencies)."""

from __future__ import annotations

from django.conf import settings

from .alerts import evaluate_realtime_thresholds
from .load import evaluate_backpressure
from .metrics import get_counter


def render_prometheus_text() -> str:
    """Counter-style metrics; use irate/rate in Prometheus from scrape deltas."""
    evaluate_realtime_thresholds()
    bp = evaluate_backpressure()

    lines: list[str] = [
        "# HELP realtime_events_dedupe_suppressed_total Dedupe window suppressions (medium/low).",
        "# TYPE realtime_events_dedupe_suppressed_total counter",
        f"realtime_events_dedupe_suppressed_total {get_counter('events_dedupe_suppressed')}",
        "# HELP realtime_redis_publish_failures_total Redis publish errors after DB write.",
        "# TYPE realtime_redis_publish_failures_total counter",
        f"realtime_redis_publish_failures_total {get_counter('redis_publish_failures')}",
        "# HELP realtime_events_redis_published_total Successful Redis publishes.",
        "# TYPE realtime_events_redis_published_total counter",
        f"realtime_events_redis_published_total {get_counter('events_redis_published')}",
        "# HELP realtime_sse_stream_opens_total SSE connections opened.",
        "# TYPE realtime_sse_stream_opens_total counter",
        f"realtime_sse_stream_opens_total {get_counter('sse_stream_opens')}",
        "# HELP realtime_sse_events_from_redis_total Events delivered via Redis path.",
        "# TYPE realtime_sse_events_from_redis_total counter",
        f"realtime_sse_events_from_redis_total {get_counter('sse_events_from_redis')}",
        "# HELP realtime_sse_events_from_db_total Events delivered via DB tail.",
        "# TYPE realtime_sse_events_from_db_total counter",
        f"realtime_sse_events_from_db_total {get_counter('sse_events_from_db')}",
        "# HELP realtime_resync_payloads_total Resync commands due to backlog.",
        "# TYPE realtime_resync_payloads_total counter",
        f"realtime_resync_payloads_total {get_counter('resync_payloads')}",
        "# HELP realtime_celery_fanout_batches_total Celery fan-out task invocations.",
        "# TYPE realtime_celery_fanout_batches_total counter",
        f"realtime_celery_fanout_batches_total {get_counter('celery_fanout_batches')}",
        "# HELP realtime_celery_fanout_latency_ms_total Sum of Celery fan-out durations (ms).",
        "# TYPE realtime_celery_fanout_latency_ms_total counter",
        f"realtime_celery_fanout_latency_ms_total {get_counter('celery_fanout_latency_ms_total')}",
        "# HELP realtime_events_persisted_total Rows inserted into realtime outbox.",
        "# TYPE realtime_events_persisted_total counter",
        f"realtime_events_persisted_total {get_counter('events_persisted_total')}",
        "# HELP realtime_events_low_priority_sampled_out_total Low-priority rows dropped by sampling.",
        "# TYPE realtime_events_low_priority_sampled_out_total counter",
        f"realtime_events_low_priority_sampled_out_total {get_counter('events_low_priority_sampled_out')}",
        "# HELP realtime_delivery_latency_ms_total Sum of emit→SSE latencies (ms).",
        "# TYPE realtime_delivery_latency_ms_total counter",
        f"realtime_delivery_latency_ms_total {get_counter('delivery_latency_ms_total')}",
        "# HELP realtime_delivery_latency_samples_total Count of latency samples.",
        "# TYPE realtime_delivery_latency_samples_total counter",
        f"realtime_delivery_latency_samples_total {get_counter('delivery_latency_samples')}",
    ]

    low = float(getattr(settings, "REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE", 1.0))
    lines.extend(
        [
            "# HELP realtime_config_low_priority_db_sample Configured low-priority DB sample rate (info).",
            "# TYPE realtime_config_low_priority_db_sample gauge",
            f"realtime_config_low_priority_db_sample {low}",
            "# HELP realtime_backpressure_level Current backpressure level (0..3).",
            "# TYPE realtime_backpressure_level gauge",
            f"realtime_backpressure_level {int(bp.level)}",
            "# HELP realtime_backpressure_low_sample_rate Effective low-priority sampling rate (0..1).",
            "# TYPE realtime_backpressure_low_sample_rate gauge",
            f"realtime_backpressure_low_sample_rate {float(bp.low_sample_rate)}",
            "# HELP realtime_backpressure_low_dedupe_seconds Effective low-priority dedupe window (s).",
            "# TYPE realtime_backpressure_low_dedupe_seconds gauge",
            f"realtime_backpressure_low_dedupe_seconds {int(bp.low_dedupe_seconds)}",
            "# HELP realtime_events_dropped_by_backpressure_total Events dropped by producer throttling under critical load.",
            "# TYPE realtime_events_dropped_by_backpressure_total counter",
            f"realtime_events_dropped_by_backpressure_total {get_counter('events_dropped_by_backpressure')}",
            "# HELP realtime_backpressure_level_samples_total Count of backpressure evaluations (approx).",
            "# TYPE realtime_backpressure_level_samples_total counter",
            f"realtime_backpressure_level_samples_total {get_counter('backpressure_level')}",
        ]
    )

    return "\n".join(lines) + "\n"
