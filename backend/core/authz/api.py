from __future__ import annotations

"""
Core authz adapter.

Initial goal: provide a stable import path for authorization that delegates to the existing
`access.services` implementation (no behavior changes).

Over time: migrate `access.*` into core, keeping domain apps decoupled from access internals.
"""

from access.services import (  # adapter: keep behavior centralized
    actor_subject_probe_for_domain_perm,
    authorize,
    can_assign_tests,
    can_edit_tests,
    can_manage_questions,
    can_view_tests,
    normalized_role,
)

__all__ = [
    "authorize",
    "can_assign_tests",
    "can_edit_tests",
    "can_manage_questions",
    "can_view_tests",
    "actor_subject_probe_for_domain_perm",
    "normalized_role",
]

