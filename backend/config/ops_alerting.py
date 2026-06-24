from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache


def _env(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def _telegram_send(*, token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as _:
        return


class AlertmanagerWebhookView(APIView):
    """
    Receives Alertmanager webhooks and forwards to Telegram.

    Env:
    - ALERTMANAGER_WEBHOOK_SECRET: optional shared secret sent as header X-Alertmanager-Secret
    - ALERT_TELEGRAM_BOT_TOKEN
    - ALERT_TELEGRAM_CHAT_ID
    """

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        secret = _env("ALERTMANAGER_WEBHOOK_SECRET")
        if secret:
            got = str(request.headers.get("X-Alertmanager-Secret") or "").strip()
            if got != secret:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        token = _env("ALERT_TELEGRAM_BOT_TOKEN")
        chat_id = _env("ALERT_TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return Response({"detail": "Telegram alerting not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = request.data
        alerts = payload.get("alerts") if isinstance(payload, dict) else None
        if not isinstance(alerts, list) or not alerts:
            return Response({"ok": True, "forwarded": 0}, status=status.HTTP_200_OK)

        # Dedupe: Alertmanager can retry; avoid spamming Telegram on transient 5xx.
        try:
            fp = str(payload.get("groupKey") or "") + ":" + str(payload.get("status") or "")
            if fp:
                key = f"ops.alertmanager.dedupe.{hash(fp)}"
                if cache.get(key):
                    return Response({"ok": True, "forwarded": 0, "deduped": True}, status=status.HTTP_200_OK)
                cache.set(key, "1", timeout=90)
        except Exception:
            pass

        # Group into a single Telegram message.
        lines: list[str] = []
        forwarded = 0
        for a in alerts[:20]:
            if not isinstance(a, dict):
                continue
            labels = a.get("labels") if isinstance(a.get("labels"), dict) else {}
            ann = a.get("annotations") if isinstance(a.get("annotations"), dict) else {}
            status_s = str(a.get("status") or "")

            name = str(labels.get("alertname") or "Alert")
            severity = str(labels.get("severity") or "unknown")
            summary = str(ann.get("summary") or ann.get("description") or "").strip()
            runbook = str(ann.get("runbook_url") or "").strip()

            chunk = f"• <b>{name}</b> (<code>{severity}</code>, <code>{status_s}</code>)"
            if summary:
                chunk += f"\n  {summary}"
            if runbook:
                chunk += f"\n  Runbook: {runbook}"
            lines.append(chunk)

        title = f"<b>Alertmanager</b> ({len(lines)} alerts, <code>{payload.get('status') or ''}</code>)"
        msg = title + "\n\n" + "\n\n".join(lines[:15])

        # Severity routing: optional per-severity chat ids.
        sev = None
        try:
            first = alerts[0] if alerts else {}
            sev = str(((first or {}).get("labels") or {}).get("severity") or "").strip().lower()
        except Exception:
            sev = None
        chat = (
            _env(f"ALERT_TELEGRAM_CHAT_ID_{sev.upper()}") if sev else ""
        ) or chat_id

        _telegram_send(token=token, chat_id=chat, text=msg)
        forwarded = 1
        return Response({"ok": True, "forwarded": forwarded}, status=status.HTTP_200_OK)

