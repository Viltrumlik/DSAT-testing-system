"""Auto-grading tests (homework rule).

Auto-graded homework (practice tests / past papers / mock exams / module tests /
quizzes) must: auto-create the submission + grade, move straight to REVIEWED, and never
sit in "Needs grading". Manual work still requires a human grade.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from exams.models import PracticeTest, TestAttempt

from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview
from classes.homework_auto_submit import (
    sync_homework_after_test_attempt_saved,
    sync_practice_submission_for_assignment,
)

User = get_user_model()


class AutoGradeFixture(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ag_owner@t.com", "secret123")
        self.classroom = Classroom.objects.create(
            name="AG", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD, created_by=self.owner
        )
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN)
        self.student = User.objects.create_user("ag_student@t.com", "secret123")
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.student, role=ClassroomMembership.ROLE_STUDENT)
        self.section = PracticeTest.objects.create(subject="MATH", label="M", title="sec", collection_name="PP")
        self.assignment = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="Practice HW",
            category=Assignment.CATEGORY_PRACTICE_TEST, practice_test=self.section,
        )

    def _complete(self, score):
        return TestAttempt.objects.create(
            student=self.student, practice_test=self.section, score=score,
            current_state="COMPLETED", is_completed=True,
            completed_at=timezone.now(), submitted_at=timezone.now(),
        )


class IsAutoGradedTests(AutoGradeFixture):
    def test_practice_is_auto_manual_is_not(self):
        self.assertTrue(self.assignment.is_auto_graded)
        manual = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="Essay",
            category=Assignment.CATEGORY_HOMEWORK, instructions="Write an essay",
        )
        self.assertFalse(manual.is_auto_graded)


class PracticeAutoGradeTests(AutoGradeFixture):
    def test_completes_to_reviewed_with_auto_grade(self):
        # Completing the attempt fires the post_save signal → auto-grades immediately.
        self._complete(700)
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(sub.status, Submission.STATUS_REVIEWED)   # Graded, not "Needs grading"
        self.assertNotEqual(sub.status, Submission.STATUS_SUBMITTED)
        review = SubmissionReview.objects.get(submission=sub)
        self.assertTrue(review.is_auto)
        self.assertEqual(float(review.grade), 700.0)
        self.assertIsNotNone(sub.submitted_at)

    def test_signal_entrypoint_auto_grades(self):
        attempt = self._complete(680)
        sync_homework_after_test_attempt_saved(attempt)
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(sub.status, Submission.STATUS_REVIEWED)
        self.assertEqual(float(sub.review.grade), 680.0)

    def test_resync_is_idempotent(self):
        self._complete(700)  # already auto-graded by the signal
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(sub.status, Submission.STATUS_REVIEWED)
        # Re-running with the same attempt makes no further change.
        self.assertFalse(sync_practice_submission_for_assignment(self.student, self.assignment))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Submission.STATUS_REVIEWED)

    def test_manual_regrade_not_overwritten_by_auto(self):
        self._complete(700)
        sync_practice_submission_for_assignment(self.student, self.assignment)
        sub = Submission.objects.get(assignment=self.assignment, student=self.student)
        review = sub.review
        review.is_auto = False
        review.grade = 800
        review.save()
        # A later re-sync must not clobber the human grade.
        sync_practice_submission_for_assignment(self.student, self.assignment)
        review.refresh_from_db()
        self.assertFalse(review.is_auto)
        self.assertEqual(float(review.grade), 800.0)
