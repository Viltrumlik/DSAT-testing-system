from __future__ import annotations

import time
from typing import Any

from django.conf import settings

from core.drills import env_flag


def get_celery_worker_snapshot(*, timeout_s: float = 0.8) -> dict[str, Any]:
    """
    Best-effort Celery worker introspection.
    Returns empty-ish structures if broker/inspect is unavailable.
    """
    broker = str(getattr(settings, "CELERY_BROKER_URL", "") or "").strip()
    if not broker or bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)):
        return {
            "enabled": False,
            "reason": "no_broker_or_eager",
            "workers": 0,
            "active_tasks": 0,
            "reserved_tasks": 0,
            "scheduled_tasks": 0,
            "active_runtime_seconds": {"avg": None, "max": None, "sample_n": 0},
        }

    if env_flag("DRILL_CELERY_STUCK"):
        # Simulate "workers up but wedged" for incident drills.
        return {
            "enabled": True,
            "reason": "drill_celery_stuck",
            "workers": 1,
            "active_tasks": 1,
            "reserved_tasks": 0,
            "scheduled_tasks": 0,
            "active_runtime_seconds": {"avg": 3600.0, "max": 3600.0, "sample_n": 1},
        }

    try:
        from config.celery import app as celery_app

        insp = celery_app.control.inspect(timeout=timeout_s)
        stats = insp.stats() or {}
        active = insp.active() or {}
        reserved = insp.reserved() or {}
        scheduled = insp.scheduled() or {}

        workers = len(stats) if isinstance(stats, dict) else 0
        active_n = sum(len(v or []) for v in (active or {}).values()) if isinstance(active, dict) else 0
        reserved_n = sum(len(v or []) for v in (reserved or {}).values()) if isinstance(reserved, dict) else 0
        scheduled_n = sum(len(v or []) for v in (scheduled or {}).values()) if isinstance(scheduled, dict) else 0

        # Compute active runtimes from Celery's time_start when present.
        now = time.time()
        runtimes: list[float] = []
        if isinstance(active, dict):
            for tasks in active.values():
                for t in tasks or []:
                    ts = t.get("time_start")
                    try:
                        if ts is not None:
                            rt = float(now - float(ts))
                            if 0 <= rt <= 7 * 24 * 3600:
                                runtimes.append(rt)
                    except Exception:
                        continue
        runtimes.sort()
        avg_rt = (sum(runtimes) / len(runtimes)) if runtimes else None
        max_rt = (max(runtimes) if runtimes else None)

        return {
            "enabled": True,
            "reason": None,
            "workers": workers,
            "active_tasks": active_n,
            "reserved_tasks": reserved_n,
            "scheduled_tasks": scheduled_n,
            "active_runtime_seconds": {"avg": avg_rt, "max": max_rt, "sample_n": len(runtimes)},
        }
    except Exception as exc:
        return {
            "enabled": True,
            "reason": f"inspect_failed: {exc.__class__.__name__}",
            "workers": 0,
            "active_tasks": 0,
            "reserved_tasks": 0,
            "scheduled_tasks": 0,
            "active_runtime_seconds": {"avg": None, "max": None, "sample_n": 0},
        }

