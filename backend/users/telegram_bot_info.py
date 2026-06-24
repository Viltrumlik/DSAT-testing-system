"""Resolve Telegram bot @username for the login widget (optional getMe fallback)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=8)
def telegram_bot_username_for_token(bot_token: str) -> str:
    if not bot_token:
        return ""
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{bot_token}/getMe")
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = json.loads(resp.read().decode())
        return str((body.get("result") or {}).get("username") or "")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, TypeError):
        return ""
