"""Ranking models — config + persisted snapshots for SAT and Academic rankings.

See docs/classroom-rebuild/BUSINESS-ARCHITECTURE.md §3. Snapshots persist computed
ranks so reads are O(1) and history/rank-change/trend are cheap. The scoring math lives
in classes/ranking/ ; these models only store inputs (config) and outputs (snapshots).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class AcademicWeightConfig(models.Model):
    """Per-classroom configurable category weights for the Academic ranking (§3.2)."""

    classroom = models.OneToOneField(
        "classes.Classroom", on_delete=models.CASCADE, related_name="academic_weights"
    )
    w_homework = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.35"))
    w_quiz = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.30"))
    w_classwork = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.20"))
    w_participation = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.15"))
    w_attendance = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    missing_as_zero = models.BooleanField(
        default=False, help_text="Teacher opt-in: count past-due ungraded work as 0 (§3.2)."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_academic_weights"

    def category_weights(self) -> dict[str, float]:
        return {
            "HOMEWORK": float(self.w_homework),
            "QUIZ": float(self.w_quiz),
            "CLASSWORK": float(self.w_classwork),
            "PARTICIPATION": float(self.w_participation),
            "ATTENDANCE": float(self.w_attendance),
        }


class ClassroomRankingConfig(models.Model):
    """Per-classroom leaderboard visibility, applies to both ranking kinds (§3.5)."""

    MODE_FULL = "FULL"
    MODE_ANONYMOUS = "ANONYMOUS"
    MODE_HIDDEN = "HIDDEN"
    MODE_CHOICES = [(MODE_FULL, "Full"), (MODE_ANONYMOUS, "Anonymous"), (MODE_HIDDEN, "Hidden")]

    classroom = models.OneToOneField(
        "classes.Classroom", on_delete=models.CASCADE, related_name="ranking_config"
    )
    leaderboard_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_FULL)
    hide_score_values = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_ranking_config"


class RankingSnapshot(models.Model):
    """One student's computed standing for a (classroom, kind, period). History via period_key."""

    KIND_SAT = "SAT"
    KIND_ACADEMIC = "ACADEMIC"
    KIND_CHOICES = [(KIND_SAT, "SAT"), (KIND_ACADEMIC, "Academic")]

    SCOPE_CLASSROOM = "CLASSROOM"
    SCOPE_CHOICES = [(SCOPE_CLASSROOM, "Classroom")]

    TREND_IMPROVING = "IMPROVING"
    TREND_STABLE = "STABLE"
    TREND_DECLINING = "DECLINING"
    TREND_CHOICES = [
        (TREND_IMPROVING, "Improving"),
        (TREND_STABLE, "Stable"),
        (TREND_DECLINING, "Declining"),
    ]

    CONFIDENCE_LOW = "LOW"
    CONFIDENCE_MEDIUM = "MEDIUM"
    CONFIDENCE_HIGH = "HIGH"
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_LOW, "Low"),
        (CONFIDENCE_MEDIUM, "Medium"),
        (CONFIDENCE_HIGH, "High"),
    ]

    classroom = models.ForeignKey(
        "classes.Classroom", on_delete=models.CASCADE, related_name="ranking_snapshots"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ranking_snapshots"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)
    scope = models.CharField(max_length=12, choices=SCOPE_CHOICES, default=SCOPE_CLASSROOM)
    period_key = models.CharField(max_length=32, db_index=True, help_text="e.g. '2026-06-13' (daily snapshot) or cycle id")

    rank = models.PositiveIntegerField()
    previous_rank = models.PositiveIntegerField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2)
    percentile = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    trend = models.CharField(max_length=10, choices=TREND_CHOICES, null=True, blank=True)
    confidence = models.CharField(max_length=8, choices=CONFIDENCE_CHOICES, null=True, blank=True)
    # Full display payload: best/latest/recent_form/peak/consistency (SAT) or
    # performance/completion/category_scores (Academic). See §3.1 / §3.2.
    components = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "classroom_ranking_snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "kind", "period_key", "student"],
                name="uniq_ranking_snapshot_per_period",
            )
        ]
        indexes = [
            models.Index(fields=["classroom", "kind", "period_key", "rank"]),
            models.Index(fields=["classroom", "kind", "student", "period_key"]),
        ]
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"{self.kind} #{self.rank} {self.student_id} @ {self.classroom_id} [{self.period_key}]"
