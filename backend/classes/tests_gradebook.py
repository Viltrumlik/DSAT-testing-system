"""Teacher gradebook tests — operational status distribution + grading source."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from exams.models import PracticeTest, TestAttempt

from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview

User = get_user_model()


class GradebookFixture(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("gb_owner@t.com", "secret123")
        self.classroom = Classroom.objects.create(
            name="GB", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD, created_by=self.owner
        )
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN)
        self.a = User.objects.create_user("gb_a@t.com", "secret123")
        self.b = User.objects.create_user("gb_b@t.com", "secret123")
        self.c = User.objects.create_user("gb_c@t.com", "secret123")
        for u in (self.a, self.b, self.c):
            ClassroomMembership.objects.create(classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT)

        # Manual assignment (file/instructions) — needs human grading.
        self.manual = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="Essay",
            category=Assignment.CATEGORY_HOMEWORK, instructions="Write", max_score=100,
        )
        # Auto assignment (practice test).
        self.section = PracticeTest.objects.create(subject="MATH", label="M", title="sec", collection_name="PP")
        self.auto = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="Practice",
            category=Assignment.CATEGORY_PRACTICE_TEST, practice_test=self.section,
        )

        # A: manual SUBMITTED (awaiting grade) + auto completed (auto-graded)
        Submission.objects.create(assignment=self.manual, student=self.a, status=Submission.STATUS_SUBMITTED, submitted_at=timezone.now())
        TestAttempt.objects.create(student=self.a, practice_test=self.section, score=700,
                                   current_state="COMPLETED", is_completed=True,
                                   completed_at=timezone.now(), submitted_at=timezone.now())
        # B: manual teacher-graded
        sub_b = Submission.objects.create(assignment=self.manual, student=self.b, status=Submission.STATUS_REVIEWED, submitted_at=timezone.now())
        SubmissionReview.objects.create(submission=sub_b, teacher=self.owner, grade=85, is_auto=False)
        # C: nothing

        self.client = APIClient()

    def _overview(self):
        return self.client.get(f"/api/classes/{self.classroom.id}/gradebook/")

    def _assignment(self, a):
        return self.client.get(f"/api/classes/{self.classroom.id}/gradebook/assignments/{a.id}/")


class GradebookPermissionTests(GradebookFixture):
    def test_student_forbidden(self):
        self.client.force_authenticate(self.a)
        self.assertEqual(self._overview().status_code, 403)
        self.assertEqual(self._assignment(self.manual).status_code, 403)


class GradebookOverviewTests(GradebookFixture):
    def test_status_distribution(self):
        self.client.force_authenticate(self.owner)
        data = self._overview().json()
        self.assertEqual(data["students"], 3)
        by_id = {r["id"]: r for r in data["assignments"]}

        manual = by_id[self.manual.id]["counts"]
        self.assertEqual(manual["graded"], 1)         # B
        self.assertEqual(manual["needs_grading"], 1)  # A submitted
        self.assertEqual(manual["missing"], 1)        # C

        auto = by_id[self.auto.id]
        self.assertTrue(auto["is_auto_graded"])
        self.assertEqual(auto["source_label"], "Practice Test")
        self.assertEqual(auto["counts"]["graded"], 1)         # A auto-graded
        self.assertEqual(auto["counts"]["needs_grading"], 0)  # auto never needs grading
        self.assertEqual(auto["counts"]["missing"], 2)        # B, C

        # class-wide needs-grading badge counts only the manual submission
        self.assertEqual(data["needs_grading_total"], 1)

    def test_auto_assignment_performance_stats(self):
        self.client.force_authenticate(self.owner)
        data = self._overview().json()
        by_id = {r["id"]: r for r in data["assignments"]}
        perf = by_id[self.auto.id]["performance"]
        self.assertEqual(perf["completed"], 1)          # only A completed
        self.assertEqual(perf["average"], 700.0)
        self.assertEqual(perf["highest"], 700.0)
        self.assertEqual(perf["lowest"], 700.0)
        self.assertAlmostEqual(perf["completion_rate"], 33.3, delta=0.1)  # 1 of 3
        # manual assignment carries no auto-performance block
        self.assertIsNone(by_id[self.manual.id]["performance"])


class GradebookRosterTests(GradebookFixture):
    def test_manual_roster_sources(self):
        self.client.force_authenticate(self.owner)
        roster = {r["student_id"]: r for r in self._assignment(self.manual).json()["roster"]}
        self.assertEqual(roster[self.a.id]["status"], "SUBMITTED")
        self.assertEqual(roster[self.b.id]["status"], "GRADED")
        self.assertEqual(roster[self.b.id]["source"], "TEACHER")
        self.assertEqual(roster[self.b.id]["grade"], "85.00")
        self.assertEqual(roster[self.c.id]["status"], "MISSING")

    def test_auto_roster_source(self):
        self.client.force_authenticate(self.owner)
        roster = {r["student_id"]: r for r in self._assignment(self.auto).json()["roster"]}
        self.assertEqual(roster[self.a.id]["status"], "GRADED")
        self.assertEqual(roster[self.a.id]["source"], "AUTO")
        self.assertEqual(float(roster[self.a.id]["grade"]), 700.0)
        self.assertEqual(roster[self.b.id]["status"], "MISSING")
