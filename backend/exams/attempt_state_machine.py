"""Explicit exam attempt transitions (SAT engine canonical path + repair whitelist)."""

from __future__ import annotations

from typing import FrozenSet

from django.core.exceptions import ValidationError


class TransitionNotAllowed(ValidationError):
    """Rejected state change (illegal edge or concurrency conflict surface)."""


def _freeze_edges() -> dict[str, FrozenSet[str]]:
    from .models import TestAttempt

    return {
        TestAttempt.STATE_NOT_STARTED: frozenset({TestAttempt.STATE_MODULE_1_ACTIVE}),
        TestAttempt.STATE_MODULE_1_ACTIVE: frozenset({TestAttempt.STATE_MODULE_2_ACTIVE, TestAttempt.STATE_SCORING}),
        TestAttempt.STATE_MODULE_2_ACTIVE: frozenset({TestAttempt.STATE_SCORING}),
        TestAttempt.STATE_SCORING: frozenset({TestAttempt.STATE_COMPLETED}),
    }


_cache: dict[str, FrozenSet[str]] | None = None


def allowed_primary_next_states(from_state: str) -> FrozenSet[str]:
    global _cache
    if _cache is None:
        _cache = _freeze_edges()
    return _cache.get(from_state, frozenset())


def assert_primary_transition_allowed(from_state: str, to_state: str) -> None:
    """Raises TransitionNotAllowed if ``from_state -> to_state`` is not an allowed canonical edge."""
    from .models import TestAttempt

    if from_state in (TestAttempt.STATE_COMPLETED, TestAttempt.STATE_ABANDONED):
        return
    ok = allowed_primary_next_states(from_state)
    if to_state not in ok:
        raise TransitionNotAllowed(
            f"Illegal exam engine transition {from_state!r} -> {to_state!r}. Allowed: {sorted(ok)}.",
        )


def assert_repair_transition_allowed(from_state: str, to_state: str) -> None:
    """Narrow whitelist for migrating legacy persisted rows during resume/admin repair."""
    from .models import TestAttempt

    repair = {
        TestAttempt.STATE_MODULE_1_SUBMITTED: frozenset({TestAttempt.STATE_MODULE_2_ACTIVE}),
        TestAttempt.STATE_MODULE_2_SUBMITTED: frozenset({TestAttempt.STATE_SCORING}),
        TestAttempt.STATE_ABANDONED: frozenset(
            {
                TestAttempt.STATE_MODULE_1_ACTIVE,
                TestAttempt.STATE_MODULE_2_ACTIVE,
                TestAttempt.STATE_NOT_STARTED,
                TestAttempt.STATE_SCORING,
            },
        ),
    }
    ok = repair.get(from_state, frozenset())
    if to_state not in ok:
        raise TransitionNotAllowed(
            f"Illegal repair transition {from_state!r} -> {to_state!r}. Allowed: {sorted(ok)}.",
        )
