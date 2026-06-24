"""Regression: creating/updating an assignment with a temp-file-backed upload must not 500.

Large uploads (> FILE_UPLOAD_MAX_MEMORY_SIZE) arrive as a disk-backed TemporaryUploadedFile
(a non-picklable BufferedRandom). The view used to ``request.data.copy()`` (a deep copy) with
the file still present, raising "cannot pickle 'BufferedRandom'". We force temp-file backing for
every upload via FILE_UPLOAD_MAX_MEMORY_SIZE=0 so even a tiny file reproduces the original crash.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from classes.models import Assignment, Classroom, ClassroomMembership

User = get_user_model()


@override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=0)
class AssignmentFileUploadTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("up_owner@t.com", "secret123")
        self.classroom = Classroom.objects.create(
            name="UP", subject=Classroom.SUBJECT_MATH, lesson_days=Classroom.DAYS_ODD, created_by=self.owner
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _url(self):
        return f"/api/classes/{self.classroom.id}/assignments/"

    def _pdf(self, name="hw.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4 test file body", content_type="application/pdf")

    def test_create_with_temp_file_upload_succeeds(self):
        resp = self.client.post(
            self._url(),
            {"title": "With file", "instructions": "do it", "attachment_file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        a = Assignment.objects.get(pk=resp.json()["id"])
        self.assertTrue(a.attachment_file)  # primary file stored

    def test_update_with_temp_file_upload_succeeds(self):
        a = Assignment.objects.create(
            classroom=self.classroom, created_by=self.owner, title="Edit me",
            category=Assignment.CATEGORY_HOMEWORK, max_score=100, status=Assignment.STATUS_DRAFT,
        )
        resp = self.client.patch(
            f"{self._url()}{a.id}/",
            {"title": "Edited", "attachment_file": self._pdf("edit.pdf")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        a.refresh_from_db()
        self.assertEqual(a.title, "Edited")
        self.assertTrue(a.attachment_file)
