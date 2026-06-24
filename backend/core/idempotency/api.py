from __future__ import annotations

"""
Core idempotency adapter.

Initial goal: provide a stable import path for idempotency that delegates to the existing
request parsing and domain implementations (no behavior changes).
"""

from typing import Callable

from rest_framework.response import Response

from config.reliability import idempotency_key_from_request
from exams.idempotency import consume_idempotency_key as _consume_exam_attempt_idem
from exams.idempotency import idempotency_ttl_seconds_for_attempt


def consume(*, attempt, endpoint: str, request, compute: Callable[[], Response], ttl_seconds: int | None = None) -> Response:
    """
    Consume an idempotency key for an attempt-scoped mutating endpoint.

    Adapter to `exams.idempotency.consume_idempotency_key` (attempt DB-backed storage).
    Default TTL spans the full seated exam duration (see ``exams.idempotency.idempotency_ttl_seconds_for_attempt``).
    """
    if ttl_seconds is None:
        resolved = idempotency_ttl_seconds_for_attempt(attempt)
    else:
        resolved = max(60, int(ttl_seconds))
    key = idempotency_key_from_request(request)
    return _consume_exam_attempt_idem(
        attempt=attempt,
        endpoint=endpoint,
        key=key,
        compute=compute,
        ttl_seconds=resolved,
    )


__all__ = ["consume", "idempotency_key_from_request"]

