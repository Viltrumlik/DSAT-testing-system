from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response


def idempotency_key_from_request(request) -> str | None:
    """
    Shared convention for idempotent mutation endpoints (retries-safe).

    Accepts RFC-style ``Idempotency-Key``, ``X-Idempotency-Key``, or WSGI ``HTTP_IDEMPOTENCY_KEY``.
    """
    meta = getattr(request, "META", {}) or {}
    try:
        h = request.headers
    except Exception:
        h = {}
    key = (
        h.get("Idempotency-Key")
        or h.get("idempotency-key")
        or meta.get("HTTP_IDEMPOTENCY_KEY")
        or h.get("X-Idempotency-Key")
        or ""
    )
    key = str(key).strip()
    return key or None


def conflict_response(
    *,
    detail: str,
    code: str,
    extra: dict | None = None,
    http_status: int = status.HTTP_409_CONFLICT,
) -> Response:
    body = {"detail": detail, "code": code}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)

