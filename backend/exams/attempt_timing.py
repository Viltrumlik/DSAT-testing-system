from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from .models import Module, TestAttempt


@dataclass(frozen=True)
class ModuleTiming:
    now: timezone.datetime
    started_at: timezone.datetime
    limit_seconds: int
    # Total seconds the student has spent paused during this module (counted
    # against neither the timer nor the deadline). Also includes any in-flight
    # pause window — the caller is expected to include it.
    paused_seconds: int = 0

    @property
    def elapsed_seconds(self) -> int:
        dt = self.now - self.started_at
        sec = int(dt.total_seconds())
        return max(0, sec - max(0, int(self.paused_seconds)))

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.limit_seconds) - self.elapsed_seconds)

    @property
    def is_expired(self) -> bool:
        return self.elapsed_seconds >= int(self.limit_seconds)


def _module_started_anchor(attempt: TestAttempt, mod: Module) -> timezone.datetime | None:
    order = int(getattr(mod, "module_order", 0) or 0)
    if order == 1:
        return getattr(attempt, "module_1_started_at", None)
    if order == 2:
        return getattr(attempt, "module_2_started_at", None)
    return None


def _accumulated_pause_seconds(attempt: TestAttempt, mod: Module, now: timezone.datetime) -> int:
    """Total seconds the student has been paused while in this module."""
    order = int(getattr(mod, "module_order", 0) or 0)
    if order == 1:
        base = int(getattr(attempt, "module_1_paused_seconds", 0) or 0)
    elif order == 2:
        base = int(getattr(attempt, "module_2_paused_seconds", 0) or 0)
    else:
        base = 0
    # Include the in-flight pause window (between pause_started_at and now)
    # so the timer doesn't appear to keep counting while the student is paused.
    pause_started_at = getattr(attempt, "pause_started_at", None)
    in_flight = 0
    if pause_started_at:
        try:
            in_flight = max(0, int((now - pause_started_at).total_seconds()))
        except Exception:
            in_flight = 0
    return base + in_flight


def get_active_module_timing(
    attempt: TestAttempt, *, now: timezone.datetime | None = None
) -> ModuleTiming | None:
    """
    Timing for the active module row. Server-authoritative: prefers per-module_started_at anchors,
    then legacy current_module_start_time. Subtracts time the student has spent
    paused so a long break doesn't burn the deadline.
    """
    mod: Module | None = getattr(attempt, "current_module", None)
    if not mod:
        return None
    started = _module_started_anchor(attempt, mod) or getattr(attempt, "current_module_start_time", None)
    if not started:
        return None
    if now is None:
        now = timezone.now()
    limit_seconds = int(getattr(mod, "time_limit_minutes", 0) or 0) * 60
    if limit_seconds <= 0:
        # Defensive: treat missing limits as "no expiry" rather than expiring instantly.
        limit_seconds = 10**9
    paused = _accumulated_pause_seconds(attempt, mod, now)
    return ModuleTiming(
        now=now,
        started_at=started,
        limit_seconds=limit_seconds,
        paused_seconds=paused,
    )
