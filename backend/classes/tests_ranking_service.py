"""Integration tests for the ranking service orchestration (DB-backed).

Validates that recompute_classroom builds inputs correctly, ranks/percentiles, persists
RankingSnapshot rows, and tracks rank_change across periods. See BUSINESS-ARCHITECTURE §3.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from exams.models import PracticeTest, TestAttempt

from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview
from classes.models_ranking import RankingSnapshot
from classes.ranking import service

User = get_user_model()


def _student(email):
    return User.objects.create_user(email, "secret123")


class SATServiceTests(TestCase):
    def setUp(self):
        self.owner = _student("w_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="Math A", subject=Classroom.SUBJECT_MATH,
            lesson_days=Classroom.DAYS_ODD, created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )
        self.section = PracticeTest.objects.create(
            subject="MATH", label="M", title="Math sec", collection_name="PP A"
        )
        # three students with distinct Math section scores
        self.s700 = _student("w700@t.com")
        self.s600 = _student("w600@t.com")
        self.s500 = _student("w500@t.com")
        for u in (self.s700, self.s600, self.s500):
            ClassroomMembership.objects.create(
                classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT
            )
        now = timezone.now()
        for u, score in ((self.s700, 700), (self.s600, 600), (self.s500, 500)):
            TestAttempt.objects.create(
                student=u, practice_test=self.section, score=score,
                current_state="COMPLETED", completed_at=now,
            )

    def test_ranks_percentiles_and_history(self):
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p1")
        snaps = {s.student_id: s for s in RankingSnapshot.objects.filter(
            classroom=self.classroom, kind=RankingSnapshot.KIND_SAT, period_key="p1")}

        self.assertEqual(len(snaps), 3)
        self.assertEqual(snaps[self.s700.id].rank, 1)
        self.assertEqual(snaps[self.s600.id].rank, 2)
        self.assertEqual(snaps[self.s500.id].rank, 3)
        # single recent event → sat score ≈ section score
        self.assertAlmostEqual(float(snaps[self.s700.id].score), 700.0, delta=1.0)
        # percentile: top→100, mid→50, low→0
        self.assertAlmostEqual(float(snaps[self.s700.id].percentile), 100.0, delta=0.1)
        self.assertAlmostEqual(float(snaps[self.s600.id].percentile), 50.0, delta=0.1)
        self.assertAlmostEqual(float(snaps[self.s500.id].percentile), 0.0, delta=0.1)
        # display components present
        comp = snaps[self.s700.id].components
        for key in ("best", "latest", "recent_form", "peak_ability", "consistency", "confidence_ratio"):
            self.assertIn(key, comp)

    def test_previous_rank_linked_across_periods(self):
        # Two recomputes with stable data → previous_rank tracks the prior period, change 0.
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p1")
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p2")
        s = RankingSnapshot.objects.get(
            classroom=self.classroom, kind=RankingSnapshot.KIND_SAT, period_key="p2", student=self.s700)
        self.assertEqual(s.rank, 1)
        self.assertEqual(s.previous_rank, 1)
        self.assertEqual(s.components.get("rank_change"), 0)


class AcademicServiceTests(TestCase):
    def setUp(self):
        self.owner = _student("a_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="Eng A", subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD, created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )
        past = timezone.now() - timedelta(days=2)
        self.hw1 = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="HW1",
            category=Assignment.CATEGORY_HOMEWORK, max_score=100, due_at=past,
        )
        self.hw2 = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="HW2",
            category=Assignment.CATEGORY_HOMEWORK, max_score=100, due_at=past,
        )
        self.full = _student("a_full@t.com")   # completes both, mean 90
        self.partial = _student("a_partial@t.com")  # completes 1 of 2, grade 90
        for u in (self.full, self.partial):
            ClassroomMembership.objects.create(
                classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT
            )
        self._grade(self.full, self.hw1, 100)
        self._grade(self.full, self.hw2, 80)
        self._grade(self.partial, self.hw1, 90)  # hw2 left missing

    def _grade(self, student, assignment, grade):
        sub = Submission.objects.create(
            assignment=assignment, student=student, status=Submission.STATUS_REVIEWED,
            submitted_at=timezone.now() - timedelta(days=1),
        )
        SubmissionReview.objects.create(submission=sub, teacher=self.owner, grade=grade)

    def test_performance_times_completion(self):
        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        snaps = {s.student_id: s for s in RankingSnapshot.objects.filter(
            classroom=self.classroom, kind=RankingSnapshot.KIND_ACADEMIC, period_key="p1")}

        # full: perf mean(100,80)=90, completion 2/2=1.0 → 90
        full = snaps[self.full.id]
        self.assertAlmostEqual(float(full.score), 90.0, delta=0.1)
        self.assertAlmostEqual(full.components["completion_factor"], 1.0, delta=0.001)

        # partial: perf 90, completion 1/2=0.5 → factor 0.60 → 54
        partial = snaps[self.partial.id]
        self.assertAlmostEqual(partial.components["performance_score"], 90.0, delta=0.1)
        self.assertAlmostEqual(partial.components["completion_factor"], 0.60, delta=0.001)
        self.assertAlmostEqual(float(partial.score), 54.0, delta=0.1)
        self.assertEqual(partial.components["missing_count"], 1)

        # ranking: full (90) ahead of partial (54)
        self.assertEqual(full.rank, 1)
        self.assertEqual(partial.rank, 2)

    def test_rank_change_on_improvement(self):
        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        # partial completes HW2 with a top grade → perf mean(90,100)=95, completion 2/2 → 95
        self._grade(self.partial, self.hw2, 100)
        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p2")
        partial = RankingSnapshot.objects.get(
            classroom=self.classroom, kind=RankingSnapshot.KIND_ACADEMIC, period_key="p2", student=self.partial)
        self.assertEqual(partial.rank, 1)          # overtakes full (95 > 90)
        self.assertEqual(partial.previous_rank, 2)
        self.assertEqual(partial.components.get("rank_change"), 1)  # 2 → 1
        self.assertEqual(partial.trend, RankingSnapshot.TREND_IMPROVING)


class RankingsApiTests(TestCase):
    def setUp(self):
        from classes.models_ranking import ClassroomRankingConfig

        self.owner = _student("api_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="Math API", subject=Classroom.SUBJECT_MATH,
            lesson_days=Classroom.DAYS_ODD, created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )
        self.section = PracticeTest.objects.create(
            subject="MATH", label="M", title="sec", collection_name="PP"
        )
        self.top = _student("api_top@t.com")
        self.low = _student("api_low@t.com")
        for u, sc in ((self.top, 760), (self.low, 540)):
            ClassroomMembership.objects.create(
                classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT
            )
            TestAttempt.objects.create(
                student=u, practice_test=self.section, score=sc,
                current_state="COMPLETED", completed_at=timezone.now(),
            )
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p1")
        self.cfg_model = ClassroomRankingConfig
        self.client = APIClient()

    def _url(self, kind="SAT"):
        return f"/api/classes/{self.classroom.id}/rankings/{kind}/"

    def test_member_only(self):
        outsider = _student("api_out@t.com")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_full_leaderboard_default(self):
        self.client.force_authenticate(self.low)
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["rows"]), 2)
        names = [row["name"] for row in body["rows"]]
        self.assertTrue(any("api_top" in n for n in names))  # FULL → names visible
        self.assertIsNotNone(body["my"])
        self.assertTrue(body["my"]["is_me"])

    def test_anonymous_hides_other_names(self):
        cfg, _ = self.cfg_model.objects.get_or_create(classroom=self.classroom)
        cfg.leaderboard_mode = self.cfg_model.MODE_ANONYMOUS
        cfg.save()
        self.client.force_authenticate(self.low)
        rows = self.client.get(self._url()).json()["rows"]
        others = [row for row in rows if not row["is_me"]]
        self.assertTrue(all(row["name"].startswith("Student #") for row in others))

    def test_hidden_mode_only_own_row(self):
        cfg, _ = self.cfg_model.objects.get_or_create(classroom=self.classroom)
        cfg.leaderboard_mode = self.cfg_model.MODE_HIDDEN
        cfg.save()
        self.client.force_authenticate(self.low)
        rows = self.client.get(self._url()).json()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_me"])

    def test_hide_scores_for_students_not_self(self):
        cfg, _ = self.cfg_model.objects.get_or_create(classroom=self.classroom)
        cfg.hide_score_values = True
        cfg.save()
        self.client.force_authenticate(self.low)
        rows = self.client.get(self._url()).json()["rows"]
        for row in rows:
            if row["is_me"]:
                self.assertIsNotNone(row["score"])   # own score always visible
            else:
                self.assertIsNone(row["score"])

    def test_recompute_requires_manager(self):
        url = f"/api/classes/{self.classroom.id}/rankings/recompute/"
        self.client.force_authenticate(self.low)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_authenticate(self.owner)
        r = self.client.post(url, {"kinds": ["SAT"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["counts"]["SAT"], 2)

    def test_config_update_requires_manager(self):
        url = f"/api/classes/{self.classroom.id}/rankings/config/"
        self.client.force_authenticate(self.low)
        self.assertEqual(self.client.patch(url, {"leaderboard_mode": "HIDDEN"}, format="json").status_code, 403)
        self.client.force_authenticate(self.owner)
        r = self.client.patch(url, {"leaderboard_mode": "ANONYMOUS", "hide_score_values": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["leaderboard_mode"], "ANONYMOUS")
        self.assertTrue(r.json()["hide_score_values"])
        # invalid mode rejected
        self.assertEqual(self.client.patch(url, {"leaderboard_mode": "BOGUS"}, format="json").status_code, 400)

    def test_history_self_and_privacy(self):
        service.recompute_classroom(self.classroom, kinds=("SAT",), period_key="p2")  # 2nd period
        self.client.force_authenticate(self.top)
        r = self.client.get(f"/api/classes/{self.classroom.id}/rankings/sat/history/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["history"]), 2)  # p1 (setUp) + p2
        # a student cannot read another student's history
        r = self.client.get(f"/api/classes/{self.classroom.id}/rankings/sat/history/?student={self.low.id}")
        self.assertEqual(r.status_code, 403)
        # staff can
        self.client.force_authenticate(self.owner)
        r = self.client.get(f"/api/classes/{self.classroom.id}/rankings/sat/history/?student={self.low.id}")
        self.assertEqual(r.status_code, 200)
