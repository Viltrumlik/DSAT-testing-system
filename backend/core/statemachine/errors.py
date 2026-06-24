from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvalidTransition(Exception):
    """
    Raised when a state transition is not allowed.
    Kept intentionally generic so domains can map it to 400/409 as needed.
    """

    message: str
    from_state: str | None = None
    to_state: str | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.from_state is not None or self.to_state is not None:
            parts.append(f"(from={self.from_state!r} to={self.to_state!r})")
        return " ".join(parts)


@dataclass(frozen=True)
class ConcurrencyConflict(Exception):
    """
    Raised when optimistic concurrency expectations fail (e.g. version mismatch).
    """

    message: str
    expected_version: int | None = None
    actual_version: int | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.expected_version is not None or self.actual_version is not None:
            parts.append(f"(expected={self.expected_version!r} actual={self.actual_version!r})")
        return " ".join(parts)

