"""Regression tests: a student REMOVED from a classroom must lose access.

Removal is a soft delete (ClassroomMembership.status = "REMOVED"). Before the fix,
the membership row still existed so the student kept seeing/entering the classroom.
These tests pin that a removed student is gone from their list AND blocked from
entry/assignments, that restoring re-grants access, and that an active/unrelated
student is unaffected.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from classes.models import Assignment, Classroom, ClassroomMembership

User = get_user_model()


def _ids(resp):
    """Classroom ids from a (possibly paginated) list response; {} on a 403."""
    if resp.status_code != 200:
        return set()
    data = resp.json()
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    return {c["id"] for c in items}


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class RemovedMemberAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("rm_owner@t.com", "pw12345678")
        self.active = User.objects.create_user("rm_active@t.com", "pw12345678")
        self.removed = User.objects.create_user("rm_removed@t.com", "pw12345678")
        self.stranger = User.objects.create_user("rm_stranger@t.com", "pw12345678")

        self.cls = Classroom.objects.create(
            name="Algebra", subject=Classroom.SUBJECT_MATH, created_by=self.owner
        )
        ClassroomMembership.objects.create(
            classroom=self.cls, user=self.owner, role=ClassroomMembership.ROLE_OWNER
        )
        ClassroomMembership.objects.create(
            classroom=self.cls, user=self.active, role=ClassroomMembership.ROLE_STUDENT
        )
        # Soft-deleted membership — the bug scenario.
        ClassroomMembership.objects.create(
            classroom=self.cls, user=self.removed, role=ClassroomMembership.ROLE_STUDENT,
            status=ClassroomMembership.STATUS_REMOVED,
        )
        self.assignment = Assignment.objects.create(
            classroom=self.cls, created_by=self.owner, title="HW1",
            category=Assignment.CATEGORY_HOMEWORK, status=Assignment.STATUS_PUBLISHED,
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    # ── active student: full access (no regression) ──────────────────────────
    def test_active_student_sees_and_enters(self):
        c = self._client(self.active)
        self.assertIn(self.cls.id, _ids(c.get("/api/classes/")))
        self.assertEqual(c.get(f"/api/classes/{self.cls.id}/").status_code, 200)
        self.assertEqual(c.get(f"/api/classes/{self.cls.id}/assignments/").status_code, 200)
        items = c.get("/api/classes/my-assignments/").json()["items"]
        self.assertIn(self.cls.id, {it["classroom_id"] for it in items})

    # ── removed student: gone + blocked ──────────────────────────────────────
    def test_removed_student_not_in_list(self):
        c = self._client(self.removed)
        self.assertNotIn(self.cls.id, _ids(c.get("/api/classes/")))

    def test_removed_student_cannot_enter_detail(self):
        c = self._client(self.removed)
        self.assertEqual(c.get(f"/api/classes/{self.cls.id}/").status_code, 403)

    def test_removed_student_cannot_see_assignments(self):
        c = self._client(self.removed)
        r = c.get(f"/api/classes/{self.cls.id}/assignments/")
        # Either the member gate 403s, or the visibility filter returns nothing —
        # in no case may the removed student see the assignment.
        self.assertNotIn(self.assignment.id, _ids(r))

    def test_removed_student_my_assignments_excludes_class(self):
        c = self._client(self.removed)
        items = c.get("/api/classes/my-assignments/").json()["items"]
        self.assertNotIn(self.cls.id, {it["classroom_id"] for it in items})

    # ── restore re-grants access ─────────────────────────────────────────────
    def test_restore_regrants_access(self):
        m = ClassroomMembership.objects.get(classroom=self.cls, user=self.removed)
        m.status = ClassroomMembership.STATUS_ACTIVE
        m.save(update_fields=["status"])
        c = self._client(self.removed)
        self.assertIn(self.cls.id, _ids(c.get("/api/classes/")))
        self.assertEqual(c.get(f"/api/classes/{self.cls.id}/").status_code, 200)

    # ── unrelated student: never had access ──────────────────────────────────
    def test_stranger_has_no_access(self):
        c = self._client(self.stranger)
        self.assertNotIn(self.cls.id, _ids(c.get("/api/classes/")))
        self.assertEqual(c.get(f"/api/classes/{self.cls.id}/").status_code, 403)
