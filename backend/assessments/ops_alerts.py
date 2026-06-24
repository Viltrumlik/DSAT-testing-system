from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger("ops.assessments")


def _parse_recipients(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def deliver_ops_alert(
    *,
    payload: dict[str, Any],
    fingerprint: str | None = None,
    persist: bool = True,
    source: str = "homework_abuse",
    alert_type: str | None = None,
    mitigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Best-effort alert delivery with retry + fallback + optional DB persistence.

    Primary: webhook (ASSESSMENT_OPS_WEBHOOK_URL or CLASSROOM_OPS_WEBHOOK_URL)
    Fallback: email (CLASSROOM_OPS_EMAIL_RECIPIENTS) if configured.
    Always: CRITICAL log line.
    """
    hook = str(getattr(settings, "ASSESSMENT_OPS_WEBHOOK_URL", "") or "").strip() or str(
        getattr(settings, "CLASSROOM_OPS_WEBHOOK_URL", "") or ""
    ).strip()
    email_to = _parse_recipients(str(getattr(settings, "CLASSROOM_OPS_EMAIL_RECIPIENTS", "") or ""))

    body = json.dumps(payload, sort_keys=True, default=str)
    logger.critical("assessments ops alert %s", body)

    webhook_ok = False
    webhook_attempts = 0
    if hook:
        try:
            import requests

            for i in range(4):
                webhook_attempts += 1
                try:
                    resp = requests.post(hook, json=payload, timeout=3)
                    if 200 <= int(resp.status_code) < 300:
                        webhook_ok = True
                        break
                except Exception:
                    pass
                time.sleep(0.25 * (2**i))
        except Exception:
            logger.exception("assessments webhook alert setup failed")

    email_ok = False
    if (not webhook_ok) and email_to:
        try:
            from django.core.mail import send_mail

            subject = "[mastersat] assessments ops alert"
            if fingerprint:
                subject += f" ({fingerprint[:80]})"
            send_mail(subject, body, None, email_to, fail_silently=True)
            email_ok = True
        except Exception:
            logger.exception("assessments email alert failed")

    alert_row_id = None
    if persist:
        try:
            from .models import SecurityAlert

            at = alert_type or str(payload.get("type") or "unknown")[:80]
            row = SecurityAlert.objects.create(
                alert_type=at,
                source=source,
                fingerprint=(fingerprint or "")[:512],
                payload=payload,
                mitigation=mitigation,
                webhook_delivered=webhook_ok,
                email_delivered=email_ok,
            )
            alert_row_id = row.pk
        except Exception:
            logger.exception("persist SecurityAlert failed")

    return {
        "webhook_configured": bool(hook),
        "webhook_ok": webhook_ok,
        "webhook_attempts": webhook_attempts,
        "email_configured": bool(email_to),
        "email_ok": email_ok,
        "persisted": bool(persist),
        "alert_row_id": alert_row_id,
    }
