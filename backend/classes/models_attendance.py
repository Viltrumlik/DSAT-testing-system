"""Attendance models — per-lesson sessions and per-student records.

See docs/classroom-rebuild/BUSINESS-ARCHITECTURE.md §4. Feeds the Academic ranking
(optional ATTENDANCE category) and analytics; SAT ignores attendance entirely.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AttendanceSession(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_FINALIZED = "FINALIZED"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_FINALIZED, "Finalized")]

    classroom = models.ForeignKey(
        "classes.Classroom", on_delete=models.CASCADE, related_name="attendance_sessions"
    )
    date = models.DateField(db_index=True)
    title = models.CharField(max_length=160, blank=True)
    lesson_index = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_attendance_sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_attendance_sessions"
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["classroom", "date"])]

    def __str__(self) -> str:
        return f"Attendance {self.classroom_id} @ {self.date}"


class AttendanceRecord(models.Model):
    STATUS_PRESENT = "PRESENT"
    STATUS_ABSENT = "ABSENT"
    STATUS_LATE = "LATE"
    STATUS_EXCUSED = "EXCUSED"
    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
        (STATUS_LATE, "Late"),
        (STATUS_EXCUSED, "Excused"),
    ]
    # Contribution weights for attendance_score (BUSINESS-ARCHITECTURE §4).
    SCORE_WEIGHT = {STATUS_PRESENT: 1.0, STATUS_LATE: 0.5, STATUS_ABSENT: 0.0}
    # EXCUSED is excluded from the denominator entirely.

    session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="records"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_records"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    note = models.CharField(max_length=240, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="marked_attendance_records"
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_attendance_records"
        unique_together = [("session", "student")]
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self) -> str:
        return f"{self.student_id} {self.status} @ {self.session_id}"
