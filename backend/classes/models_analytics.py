"""Analytics models — only what stores irreducible input data.

See docs/classroom-rebuild/BUSINESS-ARCHITECTURE.md §5. Analytics metrics are computed
live from source tables (+ RankingSnapshot history); no denormalized analytics cache is
persisted unless a measured performance problem justifies it. The only model here is
StudentGoal, which stores user *intent* (a target score), not a computed aggregate.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class StudentGoal(models.Model):
    """A student's SAT target, used for goal tracking + projection (§5)."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sat_goals"
    )
    classroom = models.ForeignKey(
        "classes.Classroom", on_delete=models.CASCADE, null=True, blank=True, related_name="student_goals"
    )
    target_total = models.PositiveIntegerField(help_text="Target full SAT score, 400–1600")
    target_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_student_goals"
        constraints = [
            models.UniqueConstraint(fields=["student", "classroom"], name="uniq_goal_per_student_classroom")
        ]

    def __str__(self) -> str:
        return f"Goal {self.target_total} for {self.student_id}"
