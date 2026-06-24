from __future__ import annotations

from collections.abc import Iterable

from .errors import ConcurrencyConflict, InvalidTransition


def require_state(*, current: str, allowed: Iterable[str], action: str) -> None:
    allowed_set = set(str(s) for s in allowed)
    if str(current) not in allowed_set:
        raise InvalidTransition(
            f"Invalid state for {action}.",
            from_state=str(current),
            to_state=None,
        )


def require_version(*, expected: int | None, actual: int | None, action: str) -> None:
    if expected is None:
        return
    try:
        ev = int(expected)
        av = int(actual or 0)
    except (TypeError, ValueError):
        raise ConcurrencyConflict(f"Invalid version numbers for {action}.", expected_version=None, actual_version=None)
    if ev != av:
        raise ConcurrencyConflict(
            f"Version conflict for {action}.",
            expected_version=ev,
            actual_version=av,
        )

