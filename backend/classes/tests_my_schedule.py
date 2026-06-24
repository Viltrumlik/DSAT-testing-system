"""Tests for GET /api/classes/my-schedule/ — the student lessons calendar.

Recurring class meetings (ODD = Mon/Wed/Fri, EVEN = Tue/Thu/Sat) from enrolled classrooms,
assigned mock/midterm test dates, and published assignment due dates — within a from/to range.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from classes.models import Classroom, ClassroomMembership
from exams.models import MockExam

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class MyScheduleTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user("sch_student@t.com", "pw12345678")
        self.owner = User.objects.create_user("sch_owner@t.com", "pw12345678")
        self.cls = Classroom.objects.create(
            name="Math ODD", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD,
            lesson_time="18:00", start_date=date(2026, 1, 1), created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.cls, user=self.student, role=ClassroomMembership.ROLE_STUDENT
        )
        # A classroom the student is NOT a member of — must not appear.
        self.other = Classroom.objects.create(
            name="Other EVEN", subject=Classroom.SUBJECT_ENGLISH, lesson_days=Classroom.DAYS_EVEN,
            start_date=date(2026, 1, 1), created_by=self.owner,
        )
        self.mock = MockExam.objects.create(
            title="June Mock", kind=MockExam.KIND_MOCK_SAT, practice_date=date(2026, 6, 15),
            is_published=True,
        )
        self.mock.assigned_users.add(self.student)
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def _events(self):
        r = self.client.get("/api/classes/my-schedule/?from=2026-06-01&to=2026-06-30")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["events"]

    def test_class_meetings_on_odd_weekdays(self):
        classes = [e for e in self._events() if e["type"] == "class"]
        # ODD = Mon/Wed/Fri; 2026-06-01 is a Monday.
        self.assertTrue(any(e["date"] == "2026-06-01" for e in classes))
        for e in classes:
            self.assertEqual(e["classroom_id"], self.cls.id)
            self.assertIn(date.fromisoformat(e["date"]).weekday(), {0, 2, 4})

    def test_mock_appears_and_membership_scoped(self):
        ev = self._events()
        self.assertTrue(any(e["type"] == "mock" and e["date"] == "2026-06-15" for e in ev))
        # The EVEN classroom the student isn't enrolled in must be excluded.
        self.assertFalse(any(e.get("classroom_id") == self.other.id for e in ev))

    def test_range_cap_enforced(self):
        r = self.client.get("/api/classes/my-schedule/?from=2026-06-01&to=2026-12-31")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["to"], "2026-08-10")  # 70 days after from
