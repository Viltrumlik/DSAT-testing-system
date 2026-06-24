"""SAT ranking math — SAT performance only (BUSINESS-ARCHITECTURE §3.1).

    SAT Score = 0.50·RecentForm + 0.30·PeakAbility + 0.20·Consistency

Pure functions over a list of scored events (one SAT "event" = a composite for a
both-subjects class, or a single section score for a subject-specific class). No DB
access here — `service.py` builds the events; this module only computes. Fully unit-testable.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

# ── Tunable constants (BUSINESS-ARCHITECTURE §3.1) ────────────────────────────
W_RECENT = 0.50
W_PEAK = 0.30
W_CONSISTENCY = 0.20

HALF_LIFE_DAYS = 180.0     # time-decay half-life for old scores
RECENT_LAMBDA = 0.70       # recency weighting within RecentForm
RECENT_K = 5               # window size for RecentForm / Consistency
PEAK_WINDOW_DAYS = 182     # "last 6 months" for PeakAbility
VOL_PENALTY = 1.0          # Consistency volatility penalty
TREND_K = 6                # events used for trend slope
TREND_EPS = 5.0            # pts/event slope band for STABLE
MIN_TRUSTED = 3            # below this → provisional / LOW confidence
FULL_TRUST_N = 5           # at/above this → HIGH confidence

# Confidence labels (mirror RankingSnapshot.CONFIDENCE_*)
CONF_LOW, CONF_MEDIUM, CONF_HIGH = "LOW", "MEDIUM", "HIGH"
TREND_UP, TREND_FLAT, TREND_DOWN = "IMPROVING", "STABLE", "DECLINING"


@dataclass(frozen=True)
class Event:
    score: float            # unit score: composite 400–1600, or section 200–800
    completed_at: datetime


def _decay(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


def _slope(scores_oldest_first: list[float]) -> float:
    """Least-squares slope of score vs. event index (0,1,2,…)."""
    m = len(scores_oldest_first)
    if m < 2:
        return 0.0
    xs = list(range(m))
    mx = sum(xs) / m
    my = sum(scores_oldest_first) / m
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mx) * (scores_oldest_first[i] - my) for i in range(m))
    return num / denom


def confidence_for(n: int) -> tuple[str, float]:
    ratio = max(0.0, min(1.0, n / FULL_TRUST_N))
    if n < MIN_TRUSTED:
        return CONF_LOW, ratio
    if n < FULL_TRUST_N:
        return CONF_MEDIUM, ratio
    return CONF_HIGH, ratio


def compute_sat(events: list[Event], *, now: datetime, lo: float, hi: float) -> dict | None:
    """Compute the SAT score + display components for one student.

    `events` may be unordered; `lo`/`hi` are the unit bounds (400/1600 composite or
    200/800 section) used to clamp Consistency. Returns None when there are no events
    (student is unranked).
    """
    if not events:
        return None

    ev = sorted(events, key=lambda e: e.completed_at, reverse=True)  # newest first
    n = len(ev)
    ages = [max((now - e.completed_at).total_seconds() / 86400.0, 0.0) for e in ev]
    scores_newest_first = [e.score for e in ev]

    # RecentForm — recency- and decay-weighted average of last k events.
    k = min(RECENT_K, n)
    weights = [(RECENT_LAMBDA ** i) * _decay(ages[i]) for i in range(k)]
    wsum = sum(weights)
    recent_window = scores_newest_first[:k]
    if wsum > 0:
        recent_form = sum(weights[i] * recent_window[i] for i in range(k)) / wsum
    else:
        recent_form = sum(recent_window) / k  # fully-decayed fallback

    # PeakAbility — best within 6 months, else decayed best overall.
    in_window = [scores_newest_first[i] for i in range(n) if ages[i] <= PEAK_WINDOW_DAYS]
    if in_window:
        peak = max(in_window)
    else:
        peak = max(scores_newest_first[i] * _decay(ages[i]) for i in range(n))

    # Consistency — recent mean penalized by volatility, clamped to unit bounds.
    mean_recent = sum(recent_window) / k
    sigma = statistics.pstdev(recent_window) if k > 1 else 0.0
    consistency = max(lo, min(hi, mean_recent - VOL_PENALTY * sigma))

    sat_score = W_RECENT * recent_form + W_PEAK * peak + W_CONSISTENCY * consistency

    # Trend — slope over the most recent TREND_K events (oldest→newest).
    trend_scores = list(reversed(scores_newest_first[: min(TREND_K, n)]))
    slope = _slope(trend_scores)
    trend = TREND_UP if slope > TREND_EPS else TREND_DOWN if slope < -TREND_EPS else TREND_FLAT

    confidence, confidence_ratio = confidence_for(n)

    return {
        "sat_score": round(sat_score, 2),
        "best": round(max(scores_newest_first), 2),
        "latest": round(scores_newest_first[0], 2),
        "recent_form": round(recent_form, 2),
        "peak_ability": round(peak, 2),
        "consistency": round(consistency, 2),
        "trend": trend,
        "slope": round(slope, 3),
        "confidence": confidence,
        "confidence_ratio": round(confidence_ratio, 3),
        "events_count": n,
    }
