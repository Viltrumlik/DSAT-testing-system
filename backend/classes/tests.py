from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from access import constants as acc_const
from access.models import UserAccess

from classes.models import (
    Classroom,
    ClassroomMembership,
    ClassPost,
    Assignment,
    Submission,
    assignment_target_practice_test_ids,
)
from classes.serializers import AssignmentSerializer

User = get_user_model()


class AssignmentTargetIdsTests(TestCase):
    def test_practice_test_ids_skips_bad_entries(self):
        admin = User.objects.create_user("targets@test.com", "secret123")
        c = Classroom.objects.create(
            name="T",
            subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=admin,
        )
        a = Assignment.objects.create(
            classroom=c,
            created_by=admin,
            title="t",
            practice_test_ids=[1, "2", "x", None],
        )
        self.assertEqual(assignment_target_practice_test_ids(a), [1, 2])


class AssignmentPracticeAccessSyncTests(TestCase):
    """Homework targeting standalone practice tests must add class students to assigned_users."""

    def setUp(self):
        from exams.models import PracticeTest

        self.admin = User.objects.create_user("apas_admin@test.com", "secret123")
        self.student = User.objects.create_user("apas_student@test.com", "secret123")
        self.classroom = Classroom.objects.create(
            name="C",
            subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=self.admin,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.admin, role=ClassroomMembership.ROLE_ADMIN
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.student, role=ClassroomMembership.ROLE_STUDENT
        )
        self.pt = PracticeTest.objects.create(
            mock_exam=None,
            subject="READING_WRITING",
            title="Standalone section",
        )

    def test_create_assignment_adds_students_to_practice_test_assigned_users(self):
        ser = AssignmentSerializer(data={"title": "Pastpaper HW", "practice_test": self.pt.pk})
        ser.is_valid(raise_exception=True)
        ser.save(classroom=self.classroom, created_by=self.admin)
        self.assertTrue(self.pt.assigned_users.filter(pk=self.student.pk).exists())


class PracticeHomeworkAutoSubmitTests(TestCase):
    """Practice-linked homework: no file uploads; completed attempts auto-submit."""

    def setUp(self):
        from exams.models import PracticeTest, TestAttempt

        self.client = APIClient()
        self.admin = User.objects.create_user("ph_auto_admin@test.com", "secret123")
        self.student = User.objects.create_user("ph_auto_student@test.com", "secret123")
        self.classroom = Classroom.objects.create(
            name="Auto class",
            subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=self.admin,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.admin, role=ClassroomMembership.ROLE_ADMIN
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.student, role=ClassroomMembership.ROLE_STUDENT
        )
        self.pt = PracticeTest.objects.create(
            mock_exam=None,
            subject="READING_WRITING",
            title="Section",
        )
        self.assignment = Assignment.objects.create(
            classroom=self.classroom,
            created_by=self.admin,
            title="Pastpaper HW",
            practice_test=self.pt,
        )
        self._TestAttempt = TestAttempt

    def test_completed_attempt_auto_grades_submission(self):
        # Auto-graded homework moves straight to REVIEWED (never sits in "Needs grading").
        att = self._TestAttempt.objects.create(
            practice_test=self.pt,
            student=self.student,
            is_completed=True,
        )
        sub = Submission.objects.filter(assignment=self.assignment, student=self.student).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, Submission.STATUS_REVIEWED)
        self.assertEqual(sub.attempt_id, att.pk)
        self.assertTrue(sub.review.is_auto)

    def test_student_can_upload_files_alongside_practice_homework(self):
        self.client.force_authenticate(self.student)
        pdf = SimpleUploadedFile("work.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        url = f"/api/classes/{self.classroom.pk}/assignments/{self.assignment.pk}/submit/"
        r = self.client.post(
            url,
            {"submit": "false", "files": pdf},
            format="multipart",
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data.get("files") or []), 1)


class ClassroomSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin_scope@test.com", "secret123")
        self.other = User.objects.create_user("other_scope@test.com", "secret123")
        self.student = User.objects.create_user("student_scope@test.com", "secret123")

        self.classroom = Classroom.objects.create(
            name="Scoped class",
            subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=self.admin,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.admin, role=ClassroomMembership.ROLE_ADMIN
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.student, role=ClassroomMembership.ROLE_STUDENT
        )

        self.assignment = Assignment.objects.create(
            classroom=self.classroom,
            created_by=self.admin,
            title="HW1",
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.STATUS_SUBMITTED,
        )

    def test_submissions_list_forbidden(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/classes/submissions/")
        self.assertEqual(r.status_code, 403)

    def test_submission_detail_requires_class_admin(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(f"/api/classes/submissions/{self.submission.pk}/")
        self.assertEqual(r.status_code, 200)

        self.client.force_authenticate(self.other)
        r2 = self.client.get(f"/api/classes/submissions/{self.submission.pk}/")
        self.assertEqual(r2.status_code, 403)

    def test_student_cannot_delete_announcement(self):
        post = ClassPost.objects.create(
            classroom=self.classroom,
            author=self.admin,
            content="<p>Hello</p>",
        )
        self.client.force_authenticate(self.student)
        r = self.client.delete(f"/api/classes/{self.classroom.pk}/posts/{post.pk}/")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(ClassPost.objects.filter(pk=post.pk).exists())

    def test_student_list_only_member_classes(self):
        other_class = Classroom.objects.create(
            name="Other class",
            subject=Classroom.SUBJECT_ENGLISH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=self.admin,
        )
        ClassroomMembership.objects.create(
            classroom=other_class, user=self.other, role=ClassroomMembership.ROLE_ADMIN
        )
        self.client.force_authenticate(self.student)
        r = self.client.get("/api/classes/")
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertIsInstance(rows, list)
        ids = {row["id"] for row in rows}
        self.assertIn(self.classroom.pk, ids)
        self.assertNotIn(other_class.pk, ids)


class ClassroomListDirectoryTests(TestCase):
    """Global assign staff should list all classrooms for homework / admin flows."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="dir_owner@example.com",
            password="secret123",
            role=acc_const.ROLE_TEACHER,
            subject=acc_const.DOMAIN_MATH,
        )
        UserAccess.objects.create(
            user=self.owner,
            subject=acc_const.DOMAIN_MATH,
            classroom=None,
            granted_by=self.owner,
        )
        self.super_admin = User.objects.create_user(
            email="dir_super@example.com",
            password="secret123",
            role=acc_const.ROLE_SUPER_ADMIN,
        )
        self.classroom = Classroom.objects.create(
            name="Remote class",
            subject=Classroom.SUBJECT_MATH,
            lesson_days=Classroom.DAYS_ODD,
            created_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom, user=self.owner, role=ClassroomMembership.ROLE_ADMIN
        )

    def test_super_admin_lists_all_classrooms_without_membership(self):
        self.assertFalse(
            ClassroomMembership.objects.filter(classroom=self.classroom, user=self.super_admin).exists()
        )
        self.client.force_authenticate(self.super_admin)
        r = self.client.get("/api/classes/directory/")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertIsInstance(data, list)
        ids = {row["id"] for row in data}
        self.assertIn(self.classroom.pk, ids)

    def test_student_cannot_list_directory_even_with_flag(self):
        student = User.objects.create_user(
            email="dir_student@example.com",
            password="secret123",
            role=acc_const.ROLE_STUDENT,
        )
        self.client.force_authenticate(student)
        r = self.client.get("/api/classes/directory/")
        self.assertEqual(r.status_code, 403)
