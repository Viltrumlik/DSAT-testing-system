from __future__ import annotations

from django.http import HttpResponse

from users.security_metrics import get


def security_metrics_prometheus() -> str:
    lines: list[str] = []

    def counter(name: str, help_text: str):
        v = get(name)
        metric = f"users_{name}_total"
        lines.append(f"# HELP {metric} {help_text}")
        lines.append(f"# TYPE {metric} counter")
        lines.append(f"{metric} {int(v)}")

    counter("failed_login", "Failed login attempts.")
    counter("refresh_fail", "Refresh failures (invalid/revoked/session missing).")
    counter("logout_revoke_fail", "Logout revoke failures.")
    counter("refresh_rotations", "Successful refresh rotations.")
    counter("suspicious_session_churn", "Suspicious session churn events.")
    counter("security_churn_alerts", "Churn risk threshold alerts (deduped).")
    counter("security_auto_revoke", "Auto session revoke on extreme churn.")

    return "\n".join(lines) + "\n"


class AdminSecurityPrometheusMetricsView:
    @staticmethod
    def as_view():
        def view(request):
            body = security_metrics_prometheus()
            return HttpResponse(body, content_type="text/plain; version=0.0.4")

        return view

