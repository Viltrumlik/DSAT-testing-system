"""Optional validation of SPA auth correlation headers vs server session (defense-in-depth)."""

from __future__ import annotations

import os
import time as time_mod

from django.http import JsonResponse

from users.auth_correlation_controls import (
    active_session_hold,
    correlate_mismatch_bump,
    correlate_mismatch_relax,
    corr_recovery_grace_ms,
    mismatch_streak_deny_threshold,
    record_correl_header_mismatch,
    should_block_for_session_hold,
)

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _skip_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return True
    prefixes = (
        "/api/health/",
        "/api/auth/csrf/",
        "/api/auth/login/",
        "/api/auth/refresh/",
        "/api/auth/client-telemetry/",
        "/api/csp-report/",
        "/api/ops/",
        "/api/schema/",
    )
    return any(path.startswith(p) for p in prefixes)


def _epoch_ms(v: object | None) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _inspect_correl(request) -> list[str]:
    """High-signal cross-checks; grace windows avoid races between cookie auth and SPA boot headers."""
    issues: list[str] = []

    boot = request.META.get("HTTP_X_MASTERSAT_AUTH_BOOT")
    active = request.META.get("HTTP_X_MASTERSAT_AUTH_LOSS_ACTIVE")
    cookie_access = getattr(request, "COOKIES", {}).get("lms_access")

    user = getattr(request, "user", None)
    authed = bool(user is not None and getattr(user, "is_authenticated", False))

    now_ms = int(time_mod.time() * 1000)

    recovery_at_ms = _epoch_ms(request.META.get("HTTP_X_MASTERSAT_AUTH_RECOVERY_AT"))

    grace_ms = corr_recovery_grace_ms()

    if boot is None and active is None:
        return issues

    if authed:
        if boot == "BOOTING":
            pass  # Warm-cache refetch overlap — common and benign.
        elif active == "1":
            transitional = recovery_at_ms is not None and 0 <= (now_ms - recovery_at_ms) < grace_ms
            if not transitional:
                issues.append("authed_but_client_loss_active")
        if boot == "UNAUTHENTICATED":
            issues.append("authed_but_client_boot_unauth")
    else:
        if cookie_access is not None and boot == "AUTHENTICATED":
            issues.append("unauthed_but_client_boot_authenticated")

    return issues


class AuthCorrelationMiddleware:
    """Log / optionally deny unsafe API calls during correlation holds or severe header mismatch."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = str(getattr(request, "path", "") or "")
        method = str(getattr(request, "method", "GET")).upper()

        if _skip_path(path) or os.getenv("AUTH_CORREL_MIDDLEWARE", "1").strip().lower() in {
            "0",
            "false",
            "no",
        }:
            return self.get_response(request)

        user = getattr(request, "user", None)
        uid = (
            int(getattr(user, "pk", 0) or 0)
            if user is not None and getattr(user, "is_authenticated", False)
            else 0
        )

        # 1) Optional hard block — elevated anomaly stress on authenticated session.
        if uid > 0 and method in UNSAFE and should_block_for_session_hold():
            hold = active_session_hold(uid)
            if hold is not None:
                return JsonResponse(
                    {"detail": "Temporary session safeguard active.", "code": "auth_correl_hold"},
                    status=403,
                )

        # 2) Header / session inconsistencies — streak accumulation + tolerant deny.
        issues = _inspect_correl(request)
        correlation_headers_seen = bool(
            request.META.get("HTTP_X_MASTERSAT_AUTH_BOOT")
            or request.META.get("HTTP_X_MASTERSAT_AUTH_LOSS_ACTIVE")
        )
        streak_after = 0
        if uid > 0 and correlation_headers_seen:
            streak_after = correlate_mismatch_bump(uid) if issues else correlate_mismatch_relax(uid)

        deny_env = os.getenv("AUTH_CORREL_REJECT_INCONSISTENT", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if issues:
            record_correl_header_mismatch(request, issues=issues)
            streak_needed = mismatch_streak_deny_threshold()
            if correlation_headers_seen and deny_env and method in UNSAFE and streak_after >= streak_needed:
                return JsonResponse(
                    {"detail": "Stale client authorization state.", "code": "auth_correl_mismatch"},
                    status=409,
                )

        return self.get_response(request)
