from __future__ import annotations

import os
import time
import uuid

from django.db import connection


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


TRACE_HEADER = "HTTP_X_TRACE_ID"
TRACE_RESPONSE_HEADER = "X-Trace-Id"


class RequestTraceMiddleware:
    """
    Attach a stable trace id to every request (propagate from X-Trace-Id when present).
    Also exposes it on the response header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        got = str(request.META.get(TRACE_HEADER) or "").strip()
        trace_id = got if got and len(got) <= 64 else uuid.uuid4().hex
        request.trace_id = trace_id
        resp = self.get_response(request)
        try:
            resp[TRACE_RESPONSE_HEADER] = trace_id
        except Exception:
            pass
        return resp


class RequestTimingMiddleware:
    """
    Lightweight tracing: log end-to-end latency + DB query count (optional).

    Enable DB query count in prod only when needed:
      TRACE_INCLUDE_DB_QUERIES=1
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.include_db_queries = _env_bool("TRACE_INCLUDE_DB_QUERIES", default=False)

    def __call__(self, request):
        t0 = time.monotonic()
        q0 = len(getattr(connection, "queries", []) or []) if self.include_db_queries else None
        resp = self.get_response(request)
        ms = int((time.monotonic() - t0) * 1000)

        try:
            if self.include_db_queries:
                q1 = len(getattr(connection, "queries", []) or [])
                resp["X-DB-Queries"] = str(max(0, int(q1) - int(q0 or 0)))
            resp["X-Response-Time-Ms"] = str(ms)
        except Exception:
            pass

        # Structured log line (logger config handles formatting).
        try:
            import logging

            logger = logging.getLogger("trace.request")
            user = getattr(request, "user", None)
            logger.info(
                "request_trace path=%s method=%s status=%s ms=%s trace_id=%s user_id=%s",
                getattr(request, "path", ""),
                getattr(request, "method", ""),
                getattr(resp, "status_code", ""),
                ms,
                getattr(request, "trace_id", ""),
                getattr(user, "pk", None),
            )
        except Exception:
            pass

        return resp

