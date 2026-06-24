from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssignmentCreated:
    assignment_id: int
    classroom_id: int | None
    actor_id: int | None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class AttemptSubmitted:
    attempt_id: int
    actor_id: int | None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class GradingCompleted:
    attempt_id: int
    actor_id: int | None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class SessionRevoked:
    user_id: int
    actor_id: int | None
    payload: dict[str, Any] | None = None

