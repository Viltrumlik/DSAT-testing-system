from __future__ import annotations

import os
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from users.models import RefreshSession, User
from users.security_audit import log_security_event, report_churn_to_ops
from users.security_metrics import get_keyed, incr, incr_keyed


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _revoke_cache_key(jti: str) -> str:
    return f"auth.revoked_refresh_jti.{jti}"


def compute_risk_score(user_id: int) -> dict:
    """
    Composite 0–100 risk score from recent behavior (1h window, cache-backed).
    """
    rotations = get_keyed("rotations_per_hour", str(user_id))
    new_sessions = get_keyed("new_sessions_per_hour", str(user_id))
    ip_uniques_rot = get_keyed("rotation_ip_unique_per_hour", str(user_id))
    ip_uniques_sess = get_keyed("session_ip_unique_per_hour", str(user_id))
    failed_refresh = get_keyed("user_failed_refresh_1h", str(user_id))

    s = 0
    s += min(35, int(rotations * 1.2))
    s += min(25, int(new_sessions * 2))
    s += min(20, int(max(ip_uniques_rot, ip_uniques_sess, 0) * 6))
    s += min(25, int(failed_refresh * 5))
    score = int(min(100, max(0, s)))

    return {
        "score": score,
        "rotations_1h": rotations,
        "new_sessions_1h": new_sessions,
        "ip_uniques_rot_1h": ip_uniques_rot,
        "ip_uniques_sess_1h": ip_uniques_sess,
        "failed_refresh_1h": failed_refresh,
    }


def record_failed_refresh_attempt(user_id: int | None) -> None:
    if user_id is None:
        return
    incr_keyed("user_failed_refresh_1h", str(int(user_id)), 1, ttl_seconds=3600)


def clear_security_step_up(*, user_id: int) -> None:
    User.objects.filter(pk=user_id, security_step_up_required_until__isnull=False).update(
        security_step_up_required_until=None
    )


def auto_revoke_all_sessions(
    *,
    user_id: int,
    request,
    reason: str,
    score: int | None = None,
    score_data: dict | None = None,
) -> None:
    now = timezone.now()
    qs = RefreshSession.objects.filter(user_id=user_id, revoked_at__isnull=True)
    for jti in list(qs.values_list("refresh_jti", flat=True)[:2000]):
        try:
            cache.set(_revoke_cache_key(str(jti)), "1", timeout=int(timedelta(days=8).total_seconds()))
        except Exception:
            pass
    qs.update(revoked_at=now)

    step_hours = _env_int("SECURITY_STEP_UP_HOURS", 24)
    User.objects.filter(pk=user_id).update(
        security_step_up_required_until=now + timedelta(hours=step_hours)
    )
    log_security_event(
        user_id=user_id,
        event_type="auto_revoke_all_sessions",
        request=request,
        detail={"reason": reason, "score": score, **(score_data or {})},
        severity="critical",
    )
    incr("security_auto_revoke", 1)


def evaluate_risk_after_session_activity(*, user_id: int, request) -> None:
    """
    After a new session or successful refresh rotation, recompute risk and optionally
    alert (deduped) and auto-revoke on extreme scores.
    """
    alert_at = _env_int("SECURITY_RISK_ALERT_THRESHOLD", 60)
    auto_at = _env_int("SECURITY_RISK_AUTO_REVOKE_THRESHOLD", 85)
    alert_dedupe = _env_int("SECURITY_RISK_ALERT_DEDUPE_SECONDS", 3600)
    auto_dedupe = _env_int("SECURITY_RISK_AUTO_REVOKE_DEDUPE_SECONDS", 3600)

    data = compute_risk_score(user_id)
    score = int(data["score"])
    if score < alert_at:
        return

    if score >= auto_at:
        ad_key = f"users.security.risk.autorevoke_dedupe.{user_id}"
        if cache.get(ad_key) is None:
            cache.set(ad_key, "1", timeout=auto_dedupe)
            auto_revoke_all_sessions(
                user_id=user_id, request=request, reason="extreme_churn", score=score, score_data=data
            )

    o_key = f"users.security.risk.alert_dedupe.{user_id}"
    if cache.get(o_key) is not None:
        return
    cache.set(o_key, "1", timeout=alert_dedupe)

    log_security_event(
        user_id=user_id,
        event_type="churn_alert_fired",
        request=request,
        detail={"score": score, **data},
        severity="warning",
    )
    report_churn_to_ops(user_id=user_id, score=score, detail=data)
    incr("security_churn_alerts", 1)
