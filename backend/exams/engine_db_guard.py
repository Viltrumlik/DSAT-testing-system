"""DB-layer conditional updates for the exam attempt row (transition safety in depth)."""

from __future__ import annotations

from typing import Any

from django.apps import apps


class TransitionConflict(Exception):
    """Row did not match expected state/version (another writer won or stale read)."""


def conditional_attempt_update(
    *,
    pk: int,
    expect_state: str,
    expect_version: int,
    updates: dict[str, Any],
) -> int:
    """
    Persist ``updates`` iff current_state/version still match expectations.
    Returns the number of rows updated (0 or 1).
    """
    TestAttempt = apps.get_model("exams", "TestAttempt")
    return int(
        TestAttempt.objects.filter(
            pk=pk,
            current_state=str(expect_state),
            version_number=int(expect_version),
        ).update(**updates)
    )


__all__ = ["conditional_attempt_update"]
