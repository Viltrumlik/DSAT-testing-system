from __future__ import annotations

from users.security_metrics import incr_keyed


def _finish(user_id: int, request) -> None:
    from users.security_risk import evaluate_risk_after_session_activity

    if request is not None:
        evaluate_risk_after_session_activity(user_id=user_id, request=request)


def observe_refresh_rotation(*, user_id: int, ip: str, request=None) -> None:
    incr_keyed("rotations_per_hour", str(user_id), 1, ttl_seconds=3600)

    ip_key = f"{user_id}.{ip}"
    ipn = incr_keyed("rotation_ip_per_hour", ip_key, 1, ttl_seconds=3600)
    if ipn == 1:
        incr_keyed("rotation_ip_unique_per_hour", str(user_id), 1, ttl_seconds=3600)

    _finish(user_id, request)


def observe_new_session(*, user_id: int, ip: str, request=None) -> None:
    """
    Counts only for risk score (new session / hour, IP spread). Do **not** run
    ``evaluate_risk_after_session_activity`` here: that used to run in the same
    request as password login, could auto-revoke + re-apply step-up, and made the
    app look "unable to log in" (tokens revoked, JWT rejected) right after a
    successful 200. Churn evaluation runs on ``observe_refresh_rotation`` only.
    """
    incr_keyed("new_sessions_per_hour", str(user_id), 1, ttl_seconds=3600)

    ip_key = f"{user_id}.{ip}"
    ipn = incr_keyed("session_ip_per_hour", ip_key, 1, ttl_seconds=3600)
    if ipn == 1:
        incr_keyed("session_ip_unique_per_hour", str(user_id), 1, ttl_seconds=3600)
