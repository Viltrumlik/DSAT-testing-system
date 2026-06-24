from __future__ import annotations

import hashlib
import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "") or "").strip() or default)
    except Exception:
        return default


def _bucket(key: str) -> int:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


class CanarySamplingMiddleware:
    """
    Deterministic canary bucketing (for edge routing).

    Env:
      CANARY_PERCENT=5  (0..100)

    Response headers:
      X-Canary-Bucket: 0|1
      X-Canary-Percent: N
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        pct = max(0, min(100, _env_int("CANARY_PERCENT", 0)))
        user = getattr(request, "user", None)
        uid = getattr(user, "pk", None)
        ip = str(getattr(request, "META", {}).get("REMOTE_ADDR") or "")[:64]
        key = str(uid) if uid is not None else (ip or "anon")
        b = 1 if (_bucket(key) < pct) else 0
        request.canary_bucket = b
        resp = self.get_response(request)
        try:
            resp["X-Canary-Bucket"] = str(b)
            resp["X-Canary-Percent"] = str(pct)
        except Exception:
            pass
        return resp

