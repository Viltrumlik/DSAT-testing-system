"""Verify Telegram Login Widget payload (https://core.telegram.org/widgets/login#checking-authorization)."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Mapping

def verify_telegram_login(
    auth_data: Mapping[str, Any],
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
) -> bool:
    """Verify Telegram Login (oauth.telegram.org / legacy widget) auth payload.

    Per Telegram, the data-check-string is built from *all* received fields except ``hash``,
    sorted alphabetically (so optional fields like ``phone_number`` are included when present).
    """
    if not bot_token or not auth_data:
        return False
    check_hash = auth_data.get("hash")
    if not check_hash:
        return False
    try:
        auth_date = int(auth_data.get("auth_date", 0))
    except (TypeError, ValueError):
        return False
    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        return False

    parts = []
    for key in sorted(k for k in auth_data if k != "hash"):
        val = auth_data[key]
        if val is None:
            continue
        if val == "":
            continue
        # Only scalar fields participate in the widget payload.
        if isinstance(val, (dict, list)):
            continue
        parts.append(f"{key}={val}")
    data_check_string = "\n".join(parts)

    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, str(check_hash))
