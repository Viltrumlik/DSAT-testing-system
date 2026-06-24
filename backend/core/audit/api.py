from __future__ import annotations

"""
Core audit adapter.

Adapter-first: provide a stable entrypoint; initially uses exams.AuditLog when available.
Over time, migrate to a unified audit table or event sink.
"""

from typing import Any

from django.utils import timezone


def audit_event(*, domain: str, action: str, actor, target: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> None:
    """
    Best-effort audit sink. Should never raise.
    """
    try:
        from exams.models import AuditLog  # local import to avoid hard dependency at import time

        AuditLog.objects.create(
            user=actor if getattr(actor, "is_authenticated", False) else None,
            action=f"{domain}.{action}",
            details=str(payload or target or {}),
            created_at=timezone.now(),
        )
    except Exception:
        # Do not block request flows on audit failures.
        return

