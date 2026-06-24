from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.response import Response

from .models import AttemptIdempotencyKey, TestAttempt
from .metrics import incr as metric_incr


def idempotency_ttl_seconds_for_attempt(attempt: TestAttempt | None) -> int:
    """
    TTL for stored replay payloads: spans a full seated exam plus buffer (autosave retries).

    Uses max(EXAM_ATTEMPT_IDEMPOTENCY_TTL_SECONDS, summed module limits + slack), capped at 7 days.
    """
    floor = int(getattr(settings, "EXAM_ATTEMPT_IDEMPOTENCY_TTL_SECONDS", 24 * 60 * 60) or 86400)
    slack = 7200  # buffer for breaks / resume jitter beyond summed module timers
    if attempt is None:
        return min(max(floor, 7200), 7 * 86400)
    try:
        total_mins = 0
        for m in attempt.practice_test.modules.all():
            total_mins += int(getattr(m, "time_limit_minutes", 0) or 0)
        scheduled_secs = total_mins * 60 + slack
    except Exception:
        scheduled_secs = 0
    return min(max(floor, scheduled_secs or 0, 7200), 7 * 86400)


@dataclass(frozen=True)
class IdempotencyResult:
    hit: bool
    response: Response | None


def consume_idempotency_key(
    *,
    attempt: TestAttempt,
    endpoint: str,
    key: str | None,
    compute: Callable[[], Response],
    ttl_seconds: int | None = None,
) -> Response:
    """
    Persist and replay responses for mutating endpoints.

    If key is None/empty, behaves like a normal compute() call.
    ``ttl_seconds`` defaults via ``idempotency_ttl_seconds_for_attempt(attempt)`` when omitted.
    """
    if ttl_seconds is None:
        ttl_seconds = idempotency_ttl_seconds_for_attempt(attempt)
    k = (key or "").strip()
    if not k:
        return compute()

    now = timezone.now()
    row = (
        AttemptIdempotencyKey.objects.filter(
            attempt=attempt,
            endpoint=endpoint,
            key=k,
        )
        .order_by("-created_at")
        .first()
    )
    if row and row.expires_at and row.expires_at > now:
        metric_incr("idempotency_replay")
        return Response(row.response_json or {}, status=int(row.response_status or 200))

    res = compute()
    try:
        AttemptIdempotencyKey.objects.create(
            attempt=attempt,
            endpoint=str(endpoint),
            key=k,
            response_status=int(getattr(res, "status_code", 200) or 200),
            response_json=getattr(res, "data", None) if isinstance(getattr(res, "data", None), (dict, list)) else {},
            expires_at=now + timezone.timedelta(seconds=int(ttl_seconds)),
        )
    except IntegrityError:
        # Another identical request already created the row (double-click / retry / network replay).
        # Replay the existing response instead of crashing with 500.
        row = (
            AttemptIdempotencyKey.objects.filter(attempt=attempt, endpoint=endpoint, key=k)
            .order_by("-created_at")
            .first()
        )
        if row and row.expires_at and row.expires_at > now:
            metric_incr("idempotency_replay")
            return Response(row.response_json or {}, status=int(row.response_status or 200))
    return res

