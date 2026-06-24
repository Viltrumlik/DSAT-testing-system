"""Assignment lifecycle tests — DRAFT/PUBLISHED/ARCHIVED (homework rebuild).

Validates student visibility, lifecycle endpoints + permissions, and ranking semantics
(archived keeps earned grades but leaves the completion denominator).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview
from classes.models_ranking import RankingSnapshot
from classes.ranking import service

User = get_user_model()


def _u(e):
    return User.objects.create_user(e, "secret123")


class HomeworkLifecycleFixture(TestCase):
    def setUp(self):
        self.owner = _u("hw_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="HW", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD, created_by=self.owner
        )
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN)
        self.student = _u("hw_student@t.com")
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.student, role=ClassroomMembership.ROLE_STUDENT)
        self.client = APIClient()

    def _mk(self, title, status):
        return Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title=title,
            category=Assignment.CATEGORY_HOMEWORK, max_score=100, status=status,
        )

    def _list_url(self):
        return f"/api/classes/{self.classroom.id}/assignments/"

    def _ids(self, resp):
        data = resp.json()
        rows = data["items"] if isinstance(data, dict) else data
        return {r["id"] for r in rows}


class VisibilityTests(HomeworkLifecycleFixture):
    def test_student_sees_only_published(self):
        self._mk("Draft one", Assignment.STATUS_DRAFT)
        pub = self._mk("Published one", Assignment.STATUS_PUBLISHED)
        self._mk("Archived one", Assignment.STATUS_ARCHIVED)
        self.client.force_authenticate(self.student)
        self.assertEqual(self._ids(self.client.get(self._list_url())), {pub.id})

    def test_staff_sees_published_and_draft_not_archived(self):
        draft = self._mk("Draft one", Assignment.STATUS_DRAFT)
        pub = self._mk("Published one", Assignment.STATUS_PUBLISHED)
        arch = self._mk("Archived one", Assignment.STATUS_ARCHIVED)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self._ids(self.client.get(self._list_url())), {draft.id, pub.id})
        # include_archived shows everything
        self.assertEqual(self._ids(self.client.get(self._list_url() + "?include_archived=1")), {draft.id, pub.id, arch.id})


class LifecycleEndpointTests(HomeworkLifecycleFixture):
    def _act(self, a, verb):
        return self.client.post(f"/api/classes/{self.classroom.id}/assignments/{a.id}/{verb}/")

    def test_student_cannot_change_lifecycle(self):
        a = self._mk("A", Assignment.STATUS_PUBLISHED)
        self.client.force_authenticate(self.student)
        self.assertEqual(self._act(a, "archive").status_code, 403)

    def test_publish_archive_unarchive(self):
        a = self._mk("A", Assignment.STATUS_DRAFT)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self._act(a, "publish").json()["status"], "PUBLISHED")
        a.refresh_from_db(); self.assertEqual(a.status, "PUBLISHED"); self.assertIsNotNone(a.published_at)
        self.assertEqual(self._act(a, "archive").json()["status"], "ARCHIVED")
        a.refresh_from_db(); self.assertEqual(a.status, "ARCHIVED")
        # unarchive must reach an archived row (hidden from the default queryset)
        self.assertEqual(self._act(a, "unarchive").json()["status"], "PUBLISHED")
        a.refresh_from_db(); self.assertEqual(a.status, "PUBLISHED")


class ArchivedRankingSemanticsTests(HomeworkLifecycleFixture):
    def test_archived_grade_retained_but_off_completion_denominator(self):
        published = self._mk("Pub HW", Assignment.STATUS_PUBLISHED)
        archived = self._mk("Old HW", Assignment.STATUS_ARCHIVED)
        for a, grade in ((published, 80), (archived, 100)):
            sub = Submission.objects.create(assignment=a, student=self.student, status=Submission.STATUS_REVIEWED,
                                            submitted_at=timezone.now() - timedelta(days=1))
            SubmissionReview.objects.create(submission=sub, teacher=self.owner, grade=grade)

        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        snap = RankingSnapshot.objects.get(classroom=self.classroom, kind="ACADEMIC", period_key="p1", student=self.student)
        # Both grades count → HOMEWORK mean(80,100)=90; completion denominator = published only (1/1) → factor 1.0
        self.assertAlmostEqual(snap.components["category_scores"]["HOMEWORK"], 90.0, delta=0.1)
        self.assertAlmostEqual(snap.components["completion_factor"], 1.0, delta=0.001)
        self.assertEqual(snap.components["missing_count"], 0)
        self.assertAlmostEqual(float(snap.score), 90.0, delta=0.1)

    def test_draft_excluded_from_academic(self):
        self._mk("Draft HW", Assignment.STATUS_DRAFT)  # no submission; must not appear as missing
        published = self._mk("Pub HW", Assignment.STATUS_PUBLISHED)
        sub = Submission.objects.create(assignment=published, student=self.student, status=Submission.STATUS_REVIEWED,
                                        submitted_at=timezone.now() - timedelta(days=1))
        SubmissionReview.objects.create(submission=sub, teacher=self.owner, grade=70)
        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        snap = RankingSnapshot.objects.get(classroom=self.classroom, kind="ACADEMIC", period_key="p1", student=self.student)
        self.assertEqual(snap.components["missing_count"], 0)  # draft not counted as assigned
        self.assertAlmostEqual(snap.components["completion_factor"], 1.0, delta=0.001)
