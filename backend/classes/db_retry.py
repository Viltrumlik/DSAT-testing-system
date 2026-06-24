"""
Retry transient database errors (deadlocks, serialization failures) on PostgreSQL.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from django.conf import settings
from django.db import OperationalError

logger = logging.getLogger("classes.db_retry")

T = TypeVar("T")


def _is_retryable_operational_error(exc: OperationalError) -> bool:
    msg = str(exc).lower()
    if "deadlock" in msg:
        return True
    if "could not serialize" in msg or "serialization failure" in msg:
        return True
    if "40001" in msg:  # SQLSTATE serialization_failure
        return True
    inner = getattr(exc, "__cause__", None)
    if inner is not None:
        pgcode = getattr(inner, "pgcode", None)
        if pgcode in ("40P01", "40001"):  # deadlock_detected, serialization_failure
            return True
    return False


def db_retry_operation(
    fn: Callable[[], T],
    *,
    max_attempts: int | None = None,
    base_delay_s: float = 0.05,
) -> T:
    """
    Run ``fn``; on retryable OperationalError, sleep with jitter and retry.
    """
    attempts = max_attempts if max_attempts is not None else int(
        getattr(settings, "CLASSROOM_DB_DEADLOCK_MAX_ATTEMPTS", 4)
    )
    last_exc: OperationalError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except OperationalError as e:
            last_exc = e
            if attempt >= attempts or not _is_retryable_operational_error(e):
                raise
            delay = base_delay_s * (2 ** (attempt - 1)) + random.random() * base_delay_s
            logger.warning(
                "db_retry_attempt attempt=%s/%s delay=%.3fs err=%s",
                attempt,
                attempts,
                delay,
                e,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
