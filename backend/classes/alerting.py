"""
Operational alerting for classroom / homework critical events.

Configure via environment (see settings):

* ``CLASSROOM_OPS_WEBHOOK_URL`` — Slack-compatible incoming webhook or generic HTTPS URL (JSON body).
* ``CLASSROOM_OPS_EMAIL_RECIPIENTS`` — comma-separated emails (uses Django ``send_mail``).

First occurrence of a fingerprint emits CRITICAL for log aggregation; duplicates within the cooldown window log WARNING only.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("classes.alerting")


def _alert_fingerprint(event: str, message: str, extra: dict[str, Any]) -> str:
    raw = json.dumps(
        {"event": event, "message": message, "extra": extra},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def notify_ops_critical(event: str, message: str, *, extra: dict[str, Any] | None = None) -> None:
    """
    Emit CRITICAL log line + optional webhook + optional email.

    Repeated identical incidents within ``CLASSROOM_ALERT_COOLDOWN_SECONDS`` only log a warning
    and skip webhook/email to avoid alert storms (still logs the first CRITICAL).

    Safe to call from request paths and Celery; failures in channels never raise.
    """
    payload = extra or {}
    cooldown = int(getattr(settings, "CLASSROOM_ALERT_COOLDOWN_SECONDS", 900) or 0)
    fp = _alert_fingerprint(event, message, payload)
    dedupe_key = f"ops_alert_dedupe:{fp}"

    if cooldown > 0:
        # First delivery wins for this fingerprint until TTL expires.
        try:
            added = cache.add(dedupe_key, 1, timeout=cooldown)
        except Exception:
            logger.exception("ops alert dedupe cache failed; delivering alert anyway")
            added = True
        if not added:
            logger.warning(
                "ops_critical_suppressed event=%s msg=%s (cooldown=%ss fingerprint=%s)",
                event,
                message,
                cooldown,
                fp,
            )
            return

    logger.critical("ops_critical event=%s msg=%s extra=%s", event, message, payload)

    webhook = (getattr(settings, "CLASSROOM_OPS_WEBHOOK_URL", None) or "").strip()
    if webhook:
        try:
            import requests

            text = f"*CRITICAL* [{event}]\n{message}"
            if payload:
                text += f"\n```{payload!r}```"
            requests.post(webhook, json={"text": text}, timeout=10)
        except Exception:
            logger.exception("CLASSROOM_OPS_WEBHOOK_URL delivery failed")

    raw_emails = getattr(settings, "CLASSROOM_OPS_EMAIL_RECIPIENTS", None)
    if raw_emails:
        recipients = [x.strip() for x in str(raw_emails).split(",") if x.strip()]
        if recipients:
            try:
                from django.core.mail import send_mail

                from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", None) or "").strip() or None
                if not from_email:
                    logger.warning("CLASSROOM_OPS_EMAIL_RECIPIENTS set but DEFAULT_FROM_EMAIL is empty; skip email")
                else:
                    subject = f"[MasterSAT CRITICAL] {event}"
                    body = f"{message}\n\n{payload!r}"
                    send_mail(
                        subject=subject[:989],
                        message=body,
                        from_email=from_email,
                        recipient_list=recipients,
                        fail_silently=False,
                    )
            except Exception:
                logger.exception("CLASSROOM_OPS_EMAIL_RECIPIENTS delivery failed")
