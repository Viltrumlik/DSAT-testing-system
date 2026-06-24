"""
Throttles for classroom homework submit: per-user, per-class, and global (system protection).

Rates come from ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`` (see settings).
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class HomeworkSubmitThrottle(UserRateThrottle):
    """Limits POST ``.../assignments/:id/submit/`` per authenticated user."""

    scope = "homework_submit"

    def allow_request(self, request, view):
        if getattr(view, "action", None) != "submit":
            return True
        allowed = super().allow_request(request, view)
        if not allowed:
            from .metrics import record_throttle_hit

            record_throttle_hit(self.scope)
        return allowed


class HomeworkSubmitGlobalThrottle(SimpleRateThrottle):
    """
    Global cap on submit requests across all users (abuse / flash crowd).
    Uses a single cache bucket (not per-IP).
    """

    scope = "homework_submit_global"

    def allow_request(self, request, view):
        if getattr(view, "action", None) != "submit":
            return True
        allowed = super().allow_request(request, view)
        if not allowed:
            from .metrics import record_throttle_hit

            record_throttle_hit(self.scope)
        return allowed

    def get_cache_key(self, request, view):
        return f"throttle_{self.scope}_all"


class HomeworkSubmitClassThrottle(SimpleRateThrottle):
    """Per-classroom cap on submit requests (protect one class from starving others)."""

    scope = "homework_submit_class"

    def allow_request(self, request, view):
        if getattr(view, "action", None) != "submit":
            return True
        allowed = super().allow_request(request, view)
        if not allowed:
            from .metrics import record_throttle_hit

            record_throttle_hit(self.scope)
        return allowed

    def get_cache_key(self, request, view):
        cid = view.kwargs.get("classroom_pk")
        ident = f"class_{cid}" if cid is not None else "class_unknown"
        return f"throttle_{self.scope}_{ident}"
