"""TA role permission matrix (the finalized capability audit).

TA can: create/edit/publish/archive assignments, grade, return, attendance, view analytics,
recompute rankings. TA cannot: delete assignments, change settings, configure ranking,
manage roster, assign TAs, delete class. Teacher can do governance except assign-TA /
delete-class (Owner-only).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from classes.models import Assignment, Classroom, ClassroomMembership, Submission

User = get_user_model()
M = ClassroomMembership


class TAMatrixFixture(TestCase):
    def setUp(self):
        def u(e):
            return User.objects.create_user(e, "secret123")
        self.owner, self.teacher, self.ta, self.student = u("ta_o@t.com"), u("ta_t@t.com"), u("ta_ta@t.com"), u("ta_s@t.com")
        self.classroom = Classroom.objects.create(
            name="TA", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD, created_by=self.owner
        )
        M.objects.create(classroom=self.classroom, user=self.owner, role=M.ROLE_OWNER)
        M.objects.create(classroom=self.classroom, user=self.teacher, role=M.ROLE_TEACHER)
        M.objects.create(classroom=self.classroom, user=self.ta, role=M.ROLE_TA)
        M.objects.create(classroom=self.classroom, user=self.student, role=M.ROLE_STUDENT)
        self.client = APIClient()

    def as_(self, who):
        self.client.force_authenticate(who)
        return self.client

    def _assignment(self, **kw):
        return Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title=kw.get("title", "HW"),
            category=Assignment.CATEGORY_HOMEWORK, instructions="x", max_score=100, **{k: v for k, v in kw.items() if k != "title"}
        )


class AssignmentMatrix(TAMatrixFixture):
    def _create_as(self, who):
        return self.as_(who).post(f"/api/classes/{self.classroom.id}/assignments/", {"title": "New"}, format="json")

    def test_ta_can_create_teacher_can_student_cannot(self):
        self.assertEqual(self._create_as(self.ta).status_code, 201)
        self.assertEqual(self._create_as(self.teacher).status_code, 201)
        self.assertEqual(self._create_as(self.student).status_code, 403)

    def test_delete_is_teacher_owner_only(self):
        a = self._assignment()
        url = f"/api/classes/{self.classroom.id}/assignments/{a.id}/"
        self.assertEqual(self.as_(self.ta).delete(url).status_code, 403)   # TA archives, not deletes
        self.assertIn(self.as_(self.teacher).delete(url).status_code, (200, 204))

    def test_ta_can_publish_and_archive(self):
        a = self._assignment(status=Assignment.STATUS_DRAFT)
        base = f"/api/classes/{self.classroom.id}/assignments/{a.id}"
        self.assertEqual(self.as_(self.ta).post(f"{base}/publish/").status_code, 200)
        self.assertEqual(self.as_(self.ta).post(f"{base}/archive/").status_code, 200)


class GradingMatrix(TAMatrixFixture):
    def test_ta_can_grade_student_cannot(self):
        a = self._assignment()
        sub = Submission.objects.create(assignment=a, student=self.student, status=Submission.STATUS_SUBMITTED, submitted_at=timezone.now())
        url = f"/api/classes/submissions/{sub.id}/grade/"
        self.assertEqual(self.as_(self.ta).post(url, {"grade": "88"}, format="json").status_code, 200)
        self.assertNotEqual(self.as_(self.student).post(url, {"grade": "10"}, format="json").status_code, 200)


class GovernanceMatrix(TAMatrixFixture):
    def test_settings_teacher_yes_ta_no(self):
        url = f"/api/classes/{self.classroom.id}/"
        self.assertEqual(self.as_(self.teacher).patch(url, {"room_number": "B2"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.ta).patch(url, {"room_number": "C3"}, format="json").status_code, 403)

    def test_ranking_config_teacher_yes_ta_no(self):
        url = f"/api/classes/{self.classroom.id}/rankings/config/"
        self.assertEqual(self.as_(self.teacher).patch(url, {"leaderboard_mode": "ANONYMOUS"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.ta).patch(url, {"leaderboard_mode": "HIDDEN"}, format="json").status_code, 403)

    def test_recompute_allowed_for_ta(self):
        self.assertEqual(self.as_(self.ta).post(f"/api/classes/{self.classroom.id}/rankings/recompute/", {}, format="json").status_code, 200)

    def test_assign_ta_owner_only(self):
        url = f"/api/classes/{self.classroom.id}/members/{self.student.id}/"
        self.assertEqual(self.as_(self.teacher).patch(url, {"role": "TA"}, format="json").status_code, 403)
        r = self.as_(self.owner).patch(url, {"role": "TA"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "TA")

    def test_remove_student_teacher_yes_ta_no(self):
        url = f"/api/classes/{self.classroom.id}/members/{self.student.id}/"
        self.assertEqual(self.as_(self.ta).patch(url, {"status": "REMOVED"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.teacher).patch(url, {"status": "REMOVED"}, format="json").status_code, 200)

    def test_owner_cannot_be_modified(self):
        url = f"/api/classes/{self.classroom.id}/members/{self.owner.id}/"
        self.assertEqual(self.as_(self.owner).patch(url, {"role": "STUDENT"}, format="json").status_code, 400)


class AttendanceMatrix(TAMatrixFixture):
    def test_ta_can_create_session(self):
        r = self.as_(self.ta).post(f"/api/classes/{self.classroom.id}/attendance/sessions/", {"date": "2026-06-15"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.as_(self.student).post(f"/api/classes/{self.classroom.id}/attendance/sessions/", {"date": "2026-06-16"}, format="json").status_code, 403)
