from __future__ import annotations

import os
import time


def env_flag(name: str) -> bool:
    v = str(os.getenv(name, "") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def env_int(name: str, default: int = 0) -> int:
    try:
        return int(str(os.getenv(name, "") or "").strip() or default)
    except Exception:
        return default


def maybe_sleep_ms(name: str) -> None:
    """
    Drill helper for injecting latency: if env var is set to N>0, sleep N ms.
    """
    ms = env_int(name, 0)
    if ms > 0:
        time.sleep(min(60_000, ms) / 1000.0)

