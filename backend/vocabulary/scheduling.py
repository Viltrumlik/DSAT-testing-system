from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ScheduleUpdate:
    ease_factor: float
    interval_days: int
    repetitions: int
    next_review_at: datetime


ALLOWED_RESULTS = frozenset({"again", "hard", "good", "easy"})


def apply_spaced_repetition(
    *,
    ease_factor: float,
    interval_days: int,
    repetitions: int,
    result: str,
    reviewed_at: datetime,
) -> ScheduleUpdate:
    """
    SM-2–inspired scheduling with four buttons (Anki-style qualities).

    again: treat as failed (q<3) — reset repetitions, shorten interval, penalize EF slightly.
    hard: pass with small interval growth and mild EF penalty vs good.
    good: standard SM-2 interval + EF update for q=4.
    easy: q=5 SM-2 EF update + boosted interval.
    """
    r = (result or "").strip().lower()
    if r not in ALLOWED_RESULTS:
        raise ValueError(f"Invalid result {result!r}; expected one of {sorted(ALLOWED_RESULTS)}")

    ef = float(ease_factor)

    if r == "again":
        return ScheduleUpdate(
            ease_factor=max(1.3, ef - 0.2),
            interval_days=0,
            repetitions=0,
            next_review_at=reviewed_at + timedelta(minutes=10),
        )

    q_map = {"hard": 3, "good": 4, "easy": 5}
    q = q_map[r]

    def sm2_ef_adjust(e: float, quality: int) -> float:
        return max(1.3, e + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

    ef = sm2_ef_adjust(ef, q)

    if r == "hard":
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = max(1, min(5, round(max(1, interval_days) * 1.25)))
        else:
            new_interval = max(1, round(max(1, interval_days) * 1.28))
        new_reps = repetitions + 1
        return ScheduleUpdate(
            ease_factor=ef,
            interval_days=int(new_interval),
            repetitions=int(new_reps),
            next_review_at=reviewed_at + timedelta(days=new_interval),
        )

    # good / easy: classical SM-2 interval steps
    prior_interval = max(0, int(interval_days))
    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = max(1, round(prior_interval * ef))

    if r == "easy":
        new_interval = max(1, round(new_interval * 1.35))
        ef = min(3.0, ef + 0.05)

    new_reps = repetitions + 1
    return ScheduleUpdate(
        ease_factor=ef,
        interval_days=int(new_interval),
        repetitions=int(new_reps),
        next_review_at=reviewed_at + timedelta(days=new_interval),
    )
