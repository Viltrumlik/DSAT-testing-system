from __future__ import annotations

import json
import os
from typing import Any

from django.core.management.base import BaseCommand

from assessments.worker_metrics import get_celery_worker_snapshot


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "") or "").strip() or default)
    except Exception:
        return default


class Command(BaseCommand):
    help = "Best-effort auto-remediation for stuck Celery workers (pool restart / purge)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print JSON result only.")
        parser.add_argument("--restart", action="store_true", help="Attempt pool restart when stuck.")
        parser.add_argument("--purge", action="store_true", help="Attempt broker queue purge when stuck.")

    def handle(self, *args, **options):
        stuck_s = _env_int("OPS_CELERY_STUCK_MAX_RUNTIME_S", 900)
        snapshot = get_celery_worker_snapshot(timeout_s=0.8)
        enabled = bool(snapshot.get("enabled"))
        max_rt = snapshot.get("active_runtime_seconds", {}).get("max")
        is_stuck = enabled and max_rt is not None and float(max_rt) >= float(stuck_s)

        actions: list[dict[str, Any]] = []

        if is_stuck and (options.get("restart") or options.get("purge")):
            try:
                from config.celery import app as celery_app

                if options.get("restart"):
                    try:
                        celery_app.control.pool_restart(reload=False)
                        actions.append({"action": "pool_restart", "ok": True})
                    except Exception as exc:
                        actions.append({"action": "pool_restart", "ok": False, "error": exc.__class__.__name__})
                if options.get("purge"):
                    try:
                        n = celery_app.control.purge()
                        actions.append({"action": "purge", "ok": True, "purged": int(n or 0)})
                    except Exception as exc:
                        actions.append({"action": "purge", "ok": False, "error": exc.__class__.__name__})
            except Exception as exc:
                actions.append({"action": "setup_failed", "ok": False, "error": exc.__class__.__name__})

        out = {
            "enabled": enabled,
            "snapshot": snapshot,
            "stuck_threshold_s": stuck_s,
            "is_stuck": bool(is_stuck),
            "actions": actions,
        }

        if options.get("json"):
            self.stdout.write(json.dumps(out, sort_keys=True, default=str))
        else:
            self.stdout.write(json.dumps(out, indent=2, sort_keys=True, default=str))

