"""Analytics tests — every value traced to real records (BUSINESS-ARCHITECTURE §5)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from exams.models import Module, PracticeTest, Question, TestAttempt

from classes import analytics
from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview
from classes.ranking import service

User = get_user_model()


def _u(email):
    return User.objects.create_user(email, "secret123")


class AnalyticsFixture(TestCase):
    def setUp(self):
        self.owner = _u("an_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="An", subject=Classroom.SUBJECT_MATH,
            lesson_days=Classroom.DAYS_ODD, created_by=self.owner,
        )
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN)
        self.s1 = _u("an_s1@t.com")
        self.s2 = _u("an_s2@t.com")
        for u in (self.s1, self.s2):
            ClassroomMembership.objects.create(classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT)
        self.section = PracticeTest.objects.create(subject="MATH", label="M", title="sec", collection_name="PP")
        now = timezone.now()
        for u, sc in ((self.s1, 700), (self.s2, 500)):
            TestAttempt.objects.create(student=u, practice_test=self.section, score=sc,
                                       current_state="COMPLETED", completed_at=now)
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p1")


class ClassAnalyticsTests(AnalyticsFixture):
    def test_real_aggregates(self):
        data = analytics.class_analytics(self.classroom)
        self.assertEqual(data["students"], 2)
        self.assertAlmostEqual(data["avg_sat_score"], 600.0, delta=2.0)   # mean(700,500)
        self.assertTrue(len(data["sat_score_distribution"]) >= 1)
        self.assertIn("sat", data["ranking_distribution"])

    def test_completion_and_submission_rates(self):
        hw = Assignment.objects.create(classroom=self.classroom, created_by=self.owner, title="HW",
                                       category=Assignment.CATEGORY_HOMEWORK, max_score=100,
                                       due_at=timezone.now() - timedelta(days=1))
        Submission.objects.create(assignment=hw, student=self.s1, status=Submission.STATUS_REVIEWED,
                                  submitted_at=timezone.now())
        data = analytics.class_analytics(self.classroom)
        rate = next(r for r in data["assignment_completion_rates"] if r["assignment_id"] == hw.id)
        self.assertEqual(rate["completed"], 1)
        self.assertEqual(rate["students"], 2)
        self.assertAlmostEqual(rate["rate"], 50.0, delta=0.1)
        self.assertAlmostEqual(data["submission_rate"], 50.0, delta=0.1)


class TopicAccuracyTests(AnalyticsFixture):
    def test_real_per_question_correctness(self):
        module = (
            Module.objects.filter(practice_test=self.section, module_order=1).first()
            or Module.objects.create(practice_test=self.section, module_order=1, time_limit_minutes=30)
        )
        existing = module.questions.count()
        q1 = Question.objects.create(module=module, question_type="MATH", correct_answers="A", order=existing + 1, question_text="q1")
        q2 = Question.objects.create(module=module, question_type="MATH", correct_answers="B", order=existing + 2, question_text="q2")
        # s1 answers q1 right, q2 wrong → Math accuracy 50%
        ta = TestAttempt.objects.filter(student=self.s1).first()
        ta.module_answers = {str(module.id): {str(q1.id): "A", str(q2.id): "C"}}
        ta.save(update_fields=["module_answers"])
        topics = analytics.sat_topic_accuracy(self.classroom, [self.s1.id])
        math = next(t for t in topics if t["topic"] == "Math")
        self.assertEqual(math["answered"], 2)
        self.assertAlmostEqual(math["accuracy"], 50.0, delta=0.1)


class StudentAnalyticsTests(AnalyticsFixture):
    def test_trends_completion_best_latest(self):
        hw = Assignment.objects.create(classroom=self.classroom, created_by=self.owner, title="HW",
                                       category=Assignment.CATEGORY_HOMEWORK, max_score=100,
                                       due_at=timezone.now() - timedelta(days=1))
        sub = Submission.objects.create(assignment=hw, student=self.s1, status=Submission.STATUS_REVIEWED,
                                        submitted_at=timezone.now())
        SubmissionReview.objects.create(submission=sub, teacher=self.owner, grade=90)

        data = analytics.student_analytics(self.classroom, self.s1)
        self.assertEqual(len(data["sat_score_trend"]), 1)
        self.assertAlmostEqual(data["completion_rate"], 100.0, delta=0.1)  # 1 of 1 academic assignment
        self.assertIsNotNone(data["best_sat_score"])
        self.assertIsNotNone(data["latest_sat_score"])
        self.assertEqual(len(data["assignment_completion_history"]), 1)
        self.assertEqual(data["recent_performance"][0]["grade"], 90.0)


class AnalyticsApiTests(AnalyticsFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, suffix):
        return f"/api/classes/{self.classroom.id}/analytics/{suffix}"

    def test_permissions(self):
        self.client.force_authenticate(self.s1)
        self.assertEqual(self.client.get(self._url("class/")).status_code, 403)   # student can't see class
        self.assertEqual(self.client.get(self._url("me/")).status_code, 200)       # own ok
        self.assertEqual(self.client.get(self._url(f"students/{self.s2.id}/")).status_code, 403)  # not own
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self._url("class/")).status_code, 200)
        self.assertEqual(self.client.get(self._url(f"students/{self.s1.id}/")).status_code, 200)
