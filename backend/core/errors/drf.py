from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .api import AppError
from core.metrics import incr, incr_role


def core_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    DRF exception handler that standardizes AppError into a stable envelope.
    Falls back to DRF default handler for everything else.
    """
    if isinstance(exc, AppError):
        body: dict = {"detail": exc.detail}
        if exc.code:
            body["code"] = exc.code
        if exc.context_id:
            body["context_id"] = exc.context_id
        st = int(getattr(exc, "status_code", 400) or 400)
        req = context.get("request") if isinstance(context, dict) else None
        actor = getattr(req, "user", None) if req is not None else None
        if st >= 500:
            incr("slo_api_5xx_total")
            incr_role("slo_api_5xx_total", actor=actor)
        elif st >= 400:
            incr("slo_api_4xx_total")
            incr_role("slo_api_4xx_total", actor=actor)
        return Response(body, status=st)

    r = drf_exception_handler(exc, context)
    # Best-effort error-rate metrics for non-AppError paths.
    if r is not None:
        try:
            st = int(getattr(r, "status_code", 0) or 0)
            req = context.get("request") if isinstance(context, dict) else None
            actor = getattr(req, "user", None) if req is not None else None
            if st >= 500:
                incr("slo_api_5xx_total")
                incr_role("slo_api_5xx_total", actor=actor)
            elif st >= 400:
                incr("slo_api_4xx_total")
                incr_role("slo_api_4xx_total", actor=actor)
        except Exception:
            pass
    return r

