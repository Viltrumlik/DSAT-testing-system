"""Unit tests for the ranking math (pure functions, no DB).

Validates the exact rules in docs/classroom-rebuild/BUSINESS-ARCHITECTURE.md §3.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from classes.ranking import academic, sat
from classes.ranking.sat import Event

NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)


def ev(score: float, days_ago: float) -> Event:
    return Event(score=score, completed_at=NOW - timedelta(days=days_ago))


class CompletionFactorTests(SimpleTestCase):
    def test_anchor_points(self):
        self.assertAlmostEqual(academic.completion_factor(1.00), 1.00, places=4)
        self.assertAlmostEqual(academic.completion_factor(0.95), 0.98, places=4)
        self.assertAlmostEqual(academic.completion_factor(0.90), 0.95, places=4)
        self.assertAlmostEqual(academic.completion_factor(0.80), 0.90, places=4)
        self.assertAlmostEqual(academic.completion_factor(0.70), 0.80, places=4)

    def test_interpolation_between_anchors(self):
        # halfway between 0.90 (0.95) and 0.95 (0.98) → 0.965
        self.assertAlmostEqual(academic.completion_factor(0.925), 0.965, places=3)

    def test_below_70_extends_to_floor(self):
        # 0.60 → 0.80 - (0.70-0.60)*1.0 = 0.70
        self.assertAlmostEqual(academic.completion_factor(0.60), 0.70, places=4)
        # very low clamps at floor 0.50
        self.assertAlmostEqual(academic.completion_factor(0.10), 0.50, places=4)

    def test_monotonic_non_decreasing(self):
        prev = 0.0
        r = 0.0
        while r <= 1.0:
            f = academic.completion_factor(r)
            self.assertGreaterEqual(f + 1e-9, prev)
            prev = f
            r += 0.05


class PerformanceScoreTests(SimpleTestCase):
    def test_renormalizes_active_weights(self):
        # Only homework + quiz have items; weights 0.35 + 0.30 renormalize to sum 1.
        percents = {"HOMEWORK": [80.0, 100.0], "QUIZ": [60.0], "CLASSWORK": [], "PARTICIPATION": []}
        weights = {"HOMEWORK": 0.35, "QUIZ": 0.30, "CLASSWORK": 0.20, "PARTICIPATION": 0.15}
        score, comp = academic.performance_score(percents, weights)
        # hw mean=90, quiz mean=60; applied weights 0.35/0.65 and 0.30/0.65
        expected = 90.0 * (0.35 / 0.65) + 60.0 * (0.30 / 0.65)
        self.assertAlmostEqual(score, round(expected, 2), places=2)
        self.assertEqual(comp["category_scores"]["HOMEWORK"], 90.0)

    def test_no_active_categories(self):
        score, comp = academic.performance_score({"HOMEWORK": []}, {"HOMEWORK": 0.35})
        self.assertEqual(score, 0.0)
        self.assertEqual(comp["applied_weights"], {})


class AcademicScoreTests(SimpleTestCase):
    def test_completion_scales_performance(self):
        out = academic.academic_score(90.0, 0.80, missing_as_zero=False)
        self.assertAlmostEqual(out["completion_factor"], 0.90, places=4)
        self.assertAlmostEqual(out["academic_score"], 81.0, places=2)

    def test_missing_as_zero_fixes_factor_to_one(self):
        out = academic.academic_score(70.0, 0.50, missing_as_zero=True)
        self.assertEqual(out["completion_factor"], 1.0)
        self.assertAlmostEqual(out["academic_score"], 70.0, places=2)


class SATTests(SimpleTestCase):
    def test_empty_is_unranked(self):
        self.assertIsNone(sat.compute_sat([], now=NOW, lo=400, hi=1600))

    def test_single_event_components(self):
        out = sat.compute_sat([ev(1400, 1)], now=NOW, lo=400, hi=1600)
        self.assertEqual(out["events_count"], 1)
        self.assertEqual(out["best"], 1400.0)
        self.assertEqual(out["latest"], 1400.0)
        # one event: recent≈peak≈consistency≈1400 (tiny time decay) → score ≈ 1400
        self.assertGreater(out["sat_score"], 1390)
        self.assertLessEqual(out["sat_score"], 1400.01)
        self.assertEqual(out["confidence"], "LOW")

    def test_recency_weighting_favors_recent(self):
        # improving student: recent high, old low
        rising = [ev(1200, 120), ev(1300, 60), ev(1500, 2)]
        out = sat.compute_sat(rising, now=NOW, lo=400, hi=1600)
        # RecentForm should sit above the plain mean (1333) because newest (1500) dominates
        self.assertGreater(out["recent_form"], 1333)
        self.assertEqual(out["trend"], "IMPROVING")
        self.assertEqual(out["best"], 1500.0)

    def test_consistency_penalizes_volatility(self):
        steady = sat.compute_sat([ev(1400, 30), ev(1410, 20), ev(1390, 10)], now=NOW, lo=400, hi=1600)
        swingy = sat.compute_sat([ev(1100, 30), ev(1600, 20), ev(1200, 10)], now=NOW, lo=400, hi=1600)
        # similar means (~1400 vs ~1300) but the steady student should have higher consistency relative to its mean
        self.assertGreater(steady["consistency"], 1380)
        self.assertLess(swingy["consistency"], swingy["sat_score"] + 1)  # volatility drags consistency below blend

    def test_confidence_tiers(self):
        self.assertEqual(sat.confidence_for(1)[0], "LOW")
        self.assertEqual(sat.confidence_for(3)[0], "MEDIUM")
        self.assertEqual(sat.confidence_for(5)[0], "HIGH")
        self.assertEqual(sat.confidence_for(9)[1], 1.0)

    def test_declining_trend(self):
        falling = [ev(1500, 120), ev(1350, 60), ev(1200, 2)]
        out = sat.compute_sat(falling, now=NOW, lo=400, hi=1600)
        self.assertEqual(out["trend"], "DECLINING")

    def test_section_unit_bounds(self):
        out = sat.compute_sat([ev(780, 5), ev(800, 1)], now=NOW, lo=200, hi=800)
        self.assertLessEqual(out["consistency"], 800)
        self.assertLessEqual(out["sat_score"], 800)
