from __future__ import annotations

import json
import logging
from typing import Any

from config.error_reporting import report_error

logger = logging.getLogger("security.audit")

def _get_models():
    from .models import SecurityAuditEvent

    return SecurityAuditEvent


def log_security_event(
    *,
    user_id: int | None,
    event_type: str,
    request=None,
    detail: dict[str, Any] | None = None,
    severity: str = "info",
) -> None:
    """
    Persist a security event and emit structured log for log shipping.
    """
    SecurityAuditEvent = _get_models()
    ip = ""
    ua = ""
    if request is not None:
        try:
            ip = str(getattr(request, "META", {}).get("REMOTE_ADDR", "") or "")[:64]
        except Exception:
            pass
        try:
            ua = str(getattr(request, "META", {}).get("HTTP_USER_AGENT", "") or "")[:512]
        except Exception:
            pass

    row = None
    try:
        if user_id is not None:
            row = SecurityAuditEvent.objects.create(
                user_id=int(user_id),
                event_type=str(event_type)[:64],
                severity=str(severity)[:16],
                ip=ip,
                user_agent=ua,
                detail=dict(detail or {}),
            )
    except Exception as exc:
        logger.exception("SecurityAuditEvent create failed: %s", exc)

    payload: dict[str, Any] = {
        "type": "security_audit",
        "event": event_type,
        "user_id": user_id,
        "severity": severity,
        "ip": ip,
    }
    if row:
        payload["id"] = row.id
    if detail:
        payload["detail"] = detail
    try:
        logger.info("%s", json.dumps(payload, default=str, sort_keys=True))
    except Exception:
        pass


def report_churn_to_ops(*, user_id: int, score: int, detail: dict[str, Any]) -> None:
    report_error("security_churn_risk", context={"user_id": user_id, "score": score, **detail})

