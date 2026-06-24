"""Seed a deterministic Classroom UAT fixture for browser acceptance testing.

Idempotent (safe to re-run). Creates one classroom with all four roles and data exercising
every rebuilt surface: assignments (draft/published/archived, manual + auto), a needs-grading
submission, a teacher-graded submission, an auto-graded practice attempt, a finalized
attendance session, and computed SAT + Academic rankings.

    python manage.py seed_classroom_uat

Logins (all password: uatpass123):
    uat_owner@mastersat.test    (Owner)
    uat_teacher@mastersat.test  (Teacher)
    uat_ta@mastersat.test       (TA)
    uat_s1@mastersat.test       (Student — has submitted + auto-graded work)
    uat_s2@mastersat.test       (Student — graded essay)
    uat_s3@mastersat.test       (Student — missing work)
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from exams.models import PracticeTest, TestAttempt

from classes.models import (
    Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview,
)
from classes.models_attendance import AttendanceRecord, AttendanceSession
from classes.ranking import service

User = get_user_model()
PW = "uatpass123"


class Command(BaseCommand):
    help = "Seed a deterministic Classroom UAT fixture (idempotent)."

    def handle(self, *args, **opts):
        def user(email, first):
            u, created = User.objects.get_or_create(email=email, defaults={"first_name": first})
            if created or not u.has_usable_password():
                u.set_password(PW)
                u.save()
            return u

        owner = user("uat_owner@mastersat.test", "Olivia")
        teacher = user("uat_teacher@mastersat.test", "Tom")
        ta = user("uat_ta@mastersat.test", "Tara")
        s1 = user("uat_s1@mastersat.test", "Sam")
        s2 = user("uat_s2@mastersat.test", "Sara")
        s3 = user("uat_s3@mastersat.test", "Sid")

        classroom, _ = Classroom.objects.get_or_create(
            name="UAT Math Class",
            defaults={"subject": Classroom.SUBJECT_MATH, "lesson_days": Classroom.DAYS_ODD, "created_by": owner},
        )

        def member(u, role):
            ClassroomMembership.objects.update_or_create(
                classroom=classroom, user=u, defaults={"role": role, "status": M.STATUS_ACTIVE}
            )
        M = ClassroomMembership
        member(owner, M.ROLE_OWNER)
        member(teacher, M.ROLE_TEACHER)
        member(ta, M.ROLE_TA)
        for s in (s1, s2, s3):
            member(s, M.ROLE_STUDENT)

        now = timezone.now()
        past = now - timedelta(days=2)

        # --- Manual assignments (statuses) ---
        essay, _ = Assignment.objects.get_or_create(
            classroom=classroom, title="Essay — argument analysis",
            defaults={"created_by": owner, "category": Assignment.CATEGORY_HOMEWORK,
                      "instructions": "Write a 300-word analysis.", "max_score": 100,
                      "status": Assignment.STATUS_PUBLISHED, "due_at": past},
        )
        Assignment.objects.get_or_create(
            classroom=classroom, title="Draft worksheet (not yet published)",
            defaults={"created_by": owner, "category": Assignment.CATEGORY_HOMEWORK,
                      "status": Assignment.STATUS_DRAFT, "max_score": 100},
        )
        Assignment.objects.get_or_create(
            classroom=classroom, title="Archived past homework",
            defaults={"created_by": owner, "category": Assignment.CATEGORY_HOMEWORK,
                      "status": Assignment.STATUS_ARCHIVED, "max_score": 100},
        )

        # s1: submitted essay (NEEDS GRADING); s2: graded essay (TEACHER); s3: missing
        sub1, _ = Submission.objects.get_or_create(
            assignment=essay, student=s1, defaults={"status": Submission.STATUS_SUBMITTED, "submitted_at": now})
        sub2, _ = Submission.objects.get_or_create(
            assignment=essay, student=s2, defaults={"status": Submission.STATUS_REVIEWED, "submitted_at": past})
        SubmissionReview.objects.get_or_create(
            submission=sub2, defaults={"teacher": teacher, "grade": 88, "max_score": 100, "feedback": "Strong thesis.", "is_auto": False})

        # --- Auto-graded practice test ---
        section, _ = PracticeTest.objects.get_or_create(
            title="UAT Math Section",
            defaults={"subject": "MATH", "label": "UAT", "collection_name": "UAT Pack"},
        )
        auto, _ = Assignment.objects.get_or_create(
            classroom=classroom, title="Practice Test — Math (auto-graded)",
            defaults={"created_by": owner, "category": Assignment.CATEGORY_PRACTICE_TEST,
                      "practice_test": section, "status": Assignment.STATUS_PUBLISHED, "due_at": past},
        )
        # s1 + s2 complete it → auto-grade fires via signal
        for s, score in ((s1, 720), (s2, 640)):
            TestAttempt.objects.get_or_create(
                student=s, practice_test=section,
                defaults={"score": score, "current_state": "COMPLETED", "is_completed": True,
                          "completed_at": now, "submitted_at": now})

        # --- Attendance: one finalized session ---
        att, _ = AttendanceSession.objects.get_or_create(
            classroom=classroom, date=now.date(),
            defaults={"title": "Lesson 1", "status": AttendanceSession.STATUS_FINALIZED, "created_by": teacher})
        for s, st in ((s1, "PRESENT"), (s2, "LATE"), (s3, "ABSENT")):
            AttendanceRecord.objects.get_or_create(
                session=att, student=s, defaults={"status": st, "marked_by": teacher})

        # --- Rankings ---
        service.recompute_classroom(classroom, kinds=("SAT", "ACADEMIC"))

        self.stdout.write(self.style.SUCCESS(
            f"UAT classroom seeded: id={classroom.id} '{classroom.name}'. "
            f"Logins (pw {PW}): owner/teacher/ta = uat_owner|uat_teacher|uat_ta@mastersat.test; "
            f"students = uat_s1|uat_s2|uat_s3@mastersat.test"
        ))
