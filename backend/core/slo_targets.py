from __future__ import annotations

"""
Hard SLO targets (runtime excellence).

These are code-owned so they can be enforced in CI/ops automation and referenced by
synthetic tests / alert rules without duplicating numbers across systems.
"""

SLO_TARGETS = {
    # Latency (ms)
    "exam_start_p95_ms": 800,
    "module_submit_p95_ms": 1200,
    "homework_assign_p95_ms": 1200,
    "login_p95_ms": 800,
    # Success rates (0..1)
    "module_submit_success_rate": 0.995,
    "homework_assign_success_rate": 0.995,
    "login_success_rate": 0.998,
    # Error rate budgets (0..1)
    "api_5xx_error_rate": 0.001,
}

__all__ = ["SLO_TARGETS"]

