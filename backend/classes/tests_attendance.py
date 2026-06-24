"""Attendance tests: scoring math, service, API, and Academic-ranking integration.

Validates BUSINESS-ARCHITECTURE §4 / §4.1.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from classes import attendance as att
from classes.models import Assignment, Classroom, ClassroomMembership, Submission, SubmissionReview
from classes.models_attendance import AttendanceRecord, AttendanceSession
from classes.models_ranking import AcademicWeightConfig, RankingSnapshot
from classes.ranking import service

User = get_user_model()
P, A, L, E = "PRESENT", "ABSENT", "LATE", "EXCUSED"


def _u(email):
    return User.objects.create_user(email, "secret123")


class AttendanceScoreMathTests(SimpleTestCase):
    def test_weights(self):
        self.assertEqual(att.compute_attendance_score([P, P, P, P]), 100.0)
        self.assertEqual(att.compute_attendance_score([P, L]), 75.0)       # (1+0.5)/2
        self.assertEqual(att.compute_attendance_score([P, A]), 50.0)
        self.assertEqual(att.compute_attendance_score([P, A, L, A]), round(100 * 1.5 / 4, 1))

    def test_excused_excluded_from_denominator(self):
        self.assertEqual(att.compute_attendance_score([P, E, A]), 50.0)    # counts [P, A]
        self.assertIsNone(att.compute_attendance_score([E, E]))            # all excused → None
        self.assertIsNone(att.compute_attendance_score([]))


class _ClassFixture(TestCase):
    def setUp(self):
        self.owner = _u("att_owner@t.com")
        self.classroom = Classroom.objects.create(
            name="Att", subject=Classroom.SUBJECT_MATH,
            lesson_days=Classroom.DAYS_ODD, created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )
        self.s1 = _u("att_s1@t.com")
        self.s2 = _u("att_s2@t.com")
        for u in (self.s1, self.s2):
            ClassroomMembership.objects.create(
                classroom=self.classroom, user=u, role=ClassroomMembership.ROLE_STUDENT
            )

    def _session(self, day_offset=0, finalized=True):
        return AttendanceSession.objects.create(
            classroom=self.classroom, date=date(2026, 6, 1) + timedelta(days=day_offset),
            status=AttendanceSession.STATUS_FINALIZED if finalized else AttendanceSession.STATUS_OPEN,
            created_by=self.owner,
        )

    def _mark(self, session, student, status):
        return AttendanceRecord.objects.create(
            session=session, student=student, status=status, marked_by=self.owner
        )


class AttendanceServiceTests(_ClassFixture):
    def test_scores_and_detail(self):
        s_a, s_b = self._session(0), self._session(1)
        self._mark(s_a, self.s1, P); self._mark(s_b, self.s1, A)   # 50
        self._mark(s_a, self.s2, P); self._mark(s_b, self.s2, P)   # 100
        scores = att.attendance_scores_for(self.classroom, [self.s1.id, self.s2.id])
        self.assertEqual(scores[self.s1.id], 50.0)
        self.assertEqual(scores[self.s2.id], 100.0)

        detail = att.student_detail(self.classroom, self.s1)
        self.assertEqual(detail["attendance_score"], 50.0)
        self.assertEqual(detail["counted_sessions"], 2)
        self.assertEqual(len(detail["history"]), 2)

    def test_open_sessions_not_counted(self):
        open_s = self._session(0, finalized=False)
        self._mark(open_s, self.s1, A)
        self.assertIsNone(att.attendance_scores_for(self.classroom, [self.s1.id])[self.s1.id])

    def test_class_summary_series(self):
        s = self._session(0)
        self._mark(s, self.s1, P); self._mark(s, self.s2, A)
        summary = att.class_summary(self.classroom)
        self.assertEqual(summary["sessions"][0]["present_rate"], 50.0)
        self.assertEqual(len(summary["students"]), 2)


class AttendanceApiTests(_ClassFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, suffix=""):
        return f"/api/classes/{self.classroom.id}/attendance/{suffix}"

    def test_student_cannot_create_session(self):
        self.client.force_authenticate(self.s1)
        r = self.client.post(self._url("sessions/"), {"date": "2026-06-02"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_full_marking_flow(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._url("sessions/"), {"date": "2026-06-02", "title": "Lesson 1"}, format="json")
        self.assertEqual(r.status_code, 201)
        sid = r.json()["id"]

        # bulk mark: s1 present, s2 excused
        r = self.client.post(self._url(f"sessions/{sid}/mark/"), {
            "records": [
                {"student_id": self.s1.id, "status": "PRESENT"},
                {"student_id": self.s2.id, "status": "EXCUSED"},
            ]}, format="json")
        self.assertEqual(r.json()["updated"], 2)

        # mark-all-present preserves the EXCUSED student
        r = self.client.post(self._url(f"sessions/{sid}/mark-all-present/"), {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            AttendanceRecord.objects.get(session_id=sid, student=self.s2).status, "EXCUSED"
        )
        self.assertEqual(
            AttendanceRecord.objects.get(session_id=sid, student=self.s1).status, "PRESENT"
        )

        # quick correction: single record update
        r = self.client.post(self._url(f"sessions/{sid}/mark/"), {
            "records": [{"student_id": self.s1.id, "status": "LATE", "note": "bus"}]}, format="json")
        self.assertEqual(AttendanceRecord.objects.get(session_id=sid, student=self.s1).status, "LATE")

        # finalize, then it counts toward the score
        self.client.post(self._url(f"sessions/{sid}/finalize/"), {}, format="json")
        self.client.force_authenticate(self.s1)
        me = self.client.get(self._url("me/")).json()
        self.assertEqual(me["attendance_score"], 50.0)  # LATE alone = 0.5 → 50

    def test_invalid_status_ignored(self):
        self.client.force_authenticate(self.owner)
        sid = self.client.post(self._url("sessions/"), {"date": "2026-06-03"}, format="json").json()["id"]
        r = self.client.post(self._url(f"sessions/{sid}/mark/"), {
            "records": [{"student_id": self.s1.id, "status": "BOGUS"}]}, format="json")
        self.assertEqual(r.json()["updated"], 0)


class AttendanceRankingIntegrationTests(_ClassFixture):
    def test_attendance_off_by_default(self):
        # graded homework only; default w_attendance=0 → attendance ignored
        self._graded_homework(self.s1, 80)
        s = self._session(0); self._mark(s, self.s1, P)
        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        snap = RankingSnapshot.objects.get(
            classroom=self.classroom, kind="ACADEMIC", period_key="p1", student=self.s1)
        self.assertNotIn("ATTENDANCE", snap.components["category_scores"])
        self.assertAlmostEqual(float(snap.score), 80.0, delta=0.1)

    def test_attendance_weighted_worked_example(self):
        # w_homework=0.35, w_attendance=0.15 → renormalize to 0.70 / 0.30
        cfg, _ = AcademicWeightConfig.objects.get_or_create(classroom=self.classroom)
        cfg.w_homework = 0.35; cfg.w_quiz = 0; cfg.w_classwork = 0
        cfg.w_participation = 0; cfg.w_attendance = 0.15
        cfg.save()
        self._graded_homework(self.s1, 80)
        s = self._session(0); self._mark(s, self.s1, P)   # attendance_score 100

        service.recompute_classroom(self.classroom, kinds=("ACADEMIC",), period_key="p1")
        snap = RankingSnapshot.objects.get(
            classroom=self.classroom, kind="ACADEMIC", period_key="p1", student=self.s1)
        cats = snap.components["category_scores"]
        self.assertEqual(cats["ATTENDANCE"], 100.0)
        self.assertEqual(cats["HOMEWORK"], 80.0)
        # 0.70*80 + 0.30*100 = 86, completion 1.0
        self.assertAlmostEqual(float(snap.score), 86.0, delta=0.1)

    def _graded_homework(self, student, grade):
        hw = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="HW",
            category=Assignment.CATEGORY_HOMEWORK, max_score=100,
            due_at=timezone.now() - timedelta(days=1),
        )
        sub = Submission.objects.create(
            assignment=hw, student=student, status=Submission.STATUS_REVIEWED,
            submitted_at=timezone.now() - timedelta(days=2),
        )
        SubmissionReview.objects.create(submission=sub, teacher=self.owner, grade=grade)
