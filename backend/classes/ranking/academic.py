"""Academic ranking math (BUSINESS-ARCHITECTURE §3.2).

    Academic Score = PerformanceScore · CompletionFactor       (0–100)

Pure functions; `service.py` supplies the normalized per-category percents and the
completion ratio from the DB. Fully unit-testable.
"""

from __future__ import annotations

# Completion-factor anchor table: completion ratio → multiplier (§3.2). Linear
# interpolation between anchors; below 0.70 the 0.70–0.80 slope continues to a 0.50 floor.
_ANCHORS = [(1.00, 1.00), (0.95, 0.98), (0.90, 0.95), (0.80, 0.90), (0.70, 0.80)]
_FLOOR = 0.50


def completion_factor(ratio: float) -> float:
    """Map completion ratio (0–1) to a multiplier in [0.50, 1.00]."""
    r = max(0.0, min(1.0, ratio))
    if r >= 1.0:
        return 1.0
    # anchors are descending by completion; find the bracketing pair
    for (hi_c, hi_f), (lo_c, lo_f) in zip(_ANCHORS, _ANCHORS[1:]):
        if lo_c <= r <= hi_c:
            span = hi_c - lo_c
            t = (r - lo_c) / span if span else 0.0
            return round(lo_f + t * (hi_f - lo_f), 4)
    # r < 0.70 : extend the 0.70→0.80 segment slope (Δfactor/Δcompletion = 1.0)
    lo_c, lo_f = 0.70, 0.80
    factor = lo_f - (lo_c - r) * 1.0
    return round(max(_FLOOR, factor), 4)


def performance_score(category_percents: dict[str, list[float]], weights: dict[str, float]) -> tuple[float, dict]:
    """Weighted average of category means over *active* categories (weight>0 and ≥1 item),
    with active weights renormalized to sum 1. Returns (score 0–100, components)."""
    active: dict[str, float] = {}
    cat_means: dict[str, float] = {}
    for cat, pcts in category_percents.items():
        w = float(weights.get(cat, 0.0))
        if w > 0 and pcts:
            cat_means[cat] = sum(pcts) / len(pcts)
            active[cat] = w

    if not active:
        return 0.0, {"category_scores": {}, "applied_weights": {}}

    total_w = sum(active.values())
    applied = {c: w / total_w for c, w in active.items()}
    score = sum(applied[c] * cat_means[c] for c in active)
    return (
        round(score, 2),
        {
            "category_scores": {c: round(cat_means[c], 2) for c in cat_means},
            "applied_weights": {c: round(applied[c], 4) for c in applied},
        },
    )


def academic_score(performance: float, completion_ratio: float, *, missing_as_zero: bool) -> dict:
    """Combine performance and completion (§3.2). When missing_as_zero is on, the missing
    items already entered PerformanceScore as 0, so CompletionFactor is fixed to 1.0."""
    factor = 1.0 if missing_as_zero else completion_factor(completion_ratio)
    return {
        "academic_score": round(performance * factor, 2),
        "performance_score": round(performance, 2),
        "completion_factor": round(factor, 4),
        "completion_rate": round(max(0.0, min(1.0, completion_ratio)) * 100, 1),
    }
