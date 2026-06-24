from __future__ import annotations

import secrets
import string

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from exams.models import MockExam, PracticeTest, PracticeTestPack, Module, TestAttempt


def _generate_join_code(length: int = 7) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Classroom(models.Model):
    SUBJECT_ENGLISH = "ENGLISH"
    SUBJECT_MATH = "MATH"
    SUBJECT_CHOICES = [
        (SUBJECT_ENGLISH, "English"),
        (SUBJECT_MATH, "Math"),
    ]

    DAYS_ODD = "ODD"
    DAYS_EVEN = "EVEN"
    DAYS_CHOICES = [
        (DAYS_ODD, "Odd days"),
        (DAYS_EVEN, "Even days"),
    ]

    name = models.CharField(max_length=120, db_index=True)
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES, db_index=True)
    description = models.TextField(
        blank=True,
        default="",
        help_text="Free-text classroom description shown to teachers and students.",
    )
    lesson_days = models.CharField(max_length=10, choices=DAYS_CHOICES, db_index=True)
    lesson_time = models.CharField(max_length=40, help_text="Example: 18:00", blank=True)
    lesson_hours = models.PositiveIntegerField(default=2, help_text="Lesson duration in hours")
    start_date = models.DateField(null=True, blank=True)
    room_number = models.CharField(max_length=30, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True)
    max_students = models.PositiveIntegerField(null=True, blank=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_classes",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_classes"
    )
    join_code = models.CharField(max_length=12, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    schedule_summary = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Optional day list for ODD groups on the class page. EVEN groups show EVEN; Monday/Saturday appear in the header.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classrooms"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def ensure_join_code(self) -> None:
        if self.join_code:
            return
        while True:
            code = _generate_join_code()
            if not Classroom.objects.filter(join_code=code).exists():
                self.join_code = code
                return

    def save(self, *args, **kwargs):
        self.ensure_join_code()
        return super().save(*args, **kwargs)


class ClassroomMembership(models.Model):
    # Classroom-local roles. ``ADMIN`` is the legacy value for the class owner/manager
    # and is retained as a stored value (capability layer treats ADMIN ≡ OWNER) so the
    # ~30 existing ``role="ADMIN"`` checks keep working; OWNER/TEACHER/TA are the
    # forward role model. A bulk ADMIN→OWNER data migration is deferred until all
    # call sites route through ``classes.capabilities`` (see BUSINESS-ARCHITECTURE §0).
    ROLE_ADMIN = "ADMIN"  # legacy owner/manager — equivalent to OWNER
    ROLE_OWNER = "OWNER"
    ROLE_TEACHER = "TEACHER"
    ROLE_TA = "TA"
    ROLE_STUDENT = "STUDENT"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin (legacy owner)"),
        (ROLE_OWNER, "Owner"),
        (ROLE_TEACHER, "Teacher"),
        (ROLE_TA, "Teaching Assistant"),
        (ROLE_STUDENT, "Student"),
    ]

    # Canonical capability sets — reference these, never compare role strings inline.
    MANAGER_ROLES = frozenset({ROLE_ADMIN, ROLE_OWNER, ROLE_TEACHER})  # full class control
    STAFF_ROLES = frozenset({ROLE_ADMIN, ROLE_OWNER, ROLE_TEACHER, ROLE_TA})  # teaching team
    GRADER_ROLES = STAFF_ROLES  # TAs may grade + take attendance

    STATUS_ACTIVE = "ACTIVE"
    STATUS_INVITED = "INVITED"
    STATUS_REMOVED = "REMOVED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INVITED, "Invited"),
        (STATUS_REMOVED, "Removed"),
    ]
    # Statuses that still count as "a member" for ACCESS gates. Removal is a soft
    # delete (status=REMOVED), so any query that decides whether the requesting user
    # may see/enter a classroom must exclude REMOVED. Keep this rule in one place.
    NON_REMOVED_STATUSES = (STATUS_ACTIVE, STATUS_INVITED)

    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_memberships"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "classroom_memberships"
        unique_together = [("classroom", "user")]
        ordering = ["role", "-joined_at"]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.classroom_id} ({self.role})"

    @property
    def is_staff_member(self) -> bool:
        return self.role in self.STAFF_ROLES

    @property
    def is_manager(self) -> bool:
        return self.role in self.MANAGER_ROLES


class ClassroomMaterial(models.Model):
    """
    Downloadable study material (PDF/DOCX) a teacher uploads to a classroom.

    Deliberately distinct from the interactive Midterm engine (``MockExam``):
    materials are plain files students download — no attempts, timing, or scoring.
    Soft-archived via ``is_active`` (mirrors ``Classroom.is_active``).
    """

    MATERIAL_EXTENSIONS = ["pdf", "doc", "docx"]

    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="materials"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_materials",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    file = models.FileField(
        upload_to="classroom_materials/",
        validators=[FileExtensionValidator(allowed_extensions=MATERIAL_EXTENSIONS)],
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_materials"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.classroom_id})"


class ClassPost(models.Model):
    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="posts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="class_posts"
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "class_posts"
        ordering = ["-created_at"]


class Assignment(models.Model):
    """
    Homework / class work. ``practice_scope`` filters which **SAT sections** count for this
    assignment (English vs Math vs both). It is **not** RBAC: authorization uses
    ``User.role``, ``User.subject`` (math|english), and ``access.UserAccess``.
    """

    PRACTICE_SCOPE_BOTH = "BOTH"
    PRACTICE_SCOPE_ENGLISH = "ENGLISH"
    PRACTICE_SCOPE_MATH = "MATH"
    PRACTICE_SCOPE_CHOICES = [
        (PRACTICE_SCOPE_BOTH, "Both (English & Math)"),
        (PRACTICE_SCOPE_ENGLISH, "English (Reading & Writing) only"),
        (PRACTICE_SCOPE_MATH, "Math only"),
    ]

    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="assignments"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_assignments"
    )
    title = models.CharField(max_length=200, db_index=True)
    instructions = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Attachments (MVP)
    mock_exam = models.ForeignKey(
        MockExam, on_delete=models.SET_NULL, null=True, blank=True, related_name="class_assignments"
    )
    practice_test = models.ForeignKey(
        PracticeTest, on_delete=models.SET_NULL, null=True, blank=True, related_name="class_assignments"
    )
    practice_test_pack = models.ForeignKey(
        PracticeTestPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_assignments",
    )
    practice_test_ids = models.JSONField(null=True, blank=True)
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="class_assignments"
    )
    external_url = models.URLField(blank=True)
    attachment_file = models.FileField(upload_to="homework_files/", null=True, blank=True)
    practice_scope = models.CharField(
        max_length=20,
        choices=PRACTICE_SCOPE_CHOICES,
        default=PRACTICE_SCOPE_BOTH,
        help_text="For mock or pastpaper with multiple sections: assign all, English only, or Math only.",
    )

    # Ranking routing (BUSINESS-ARCHITECTURE §3.4): SAT-scored categories feed SAT
    # (via TestAttempt) and are excluded from Academic; the rest feed Academic via grades.
    CATEGORY_HOMEWORK = "HOMEWORK"
    CATEGORY_CLASSWORK = "CLASSWORK"
    CATEGORY_QUIZ = "QUIZ"
    CATEGORY_PARTICIPATION = "PARTICIPATION"
    CATEGORY_PRACTICE_TEST = "PRACTICE_TEST"
    CATEGORY_MOCK_EXAM = "MOCK_EXAM"
    CATEGORY_PAST_PAPER = "PAST_PAPER"
    CATEGORY_CHOICES = [
        (CATEGORY_HOMEWORK, "Homework"),
        (CATEGORY_CLASSWORK, "Classwork"),
        (CATEGORY_QUIZ, "Quiz"),
        (CATEGORY_PARTICIPATION, "Participation"),
        (CATEGORY_PRACTICE_TEST, "Practice test"),
        (CATEGORY_MOCK_EXAM, "Mock exam"),
        (CATEGORY_PAST_PAPER, "Past paper"),
    ]
    # Categories whose outcome is a SAT scaled score → SAT ranking only.
    SAT_CATEGORIES = frozenset({CATEGORY_PRACTICE_TEST, CATEGORY_MOCK_EXAM, CATEGORY_PAST_PAPER})
    # Categories that contribute to the Academic ranking (graded work).
    ACADEMIC_CATEGORIES = frozenset(
        {CATEGORY_HOMEWORK, CATEGORY_CLASSWORK, CATEGORY_QUIZ, CATEGORY_PARTICIPATION}
    )

    # Assignment lifecycle (BUSINESS-ARCHITECTURE homework rebuild). DRAFT = teacher
    # authoring (invisible to students, counts nowhere); PUBLISHED = live; ARCHIVED =
    # retired (hidden from active lists, read-only; existing grades retained but dropped
    # from the completion/"missing" denominator).
    STATUS_DRAFT = "DRAFT"
    STATUS_PUBLISHED = "PUBLISHED"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_HOMEWORK,
        db_index=True,
        help_text="Routes the result to SAT or Academic ranking. See BUSINESS-ARCHITECTURE §3.4.",
    )
    max_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Points this work is graded out of; required to normalize teacher grades for Academic ranking.",
    )

    # Default PUBLISHED so existing rows + the current quick-create flow stay visible.
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_PUBLISHED, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_assignments"
        ordering = ["-created_at"]

    @property
    def is_visible_to_students(self) -> bool:
        return self.status == self.STATUS_PUBLISHED

    @property
    def content_count(self) -> int:
        """How many distinct openable contents are attached (file, pastpaper, assessment,
        practice test, etc.). Drives the 'bundle'/instructional behavior: an assignment can
        bundle several contents at once and students open each one separately."""
        n = 0
        if self.mock_exam_id:
            n += 1
        if self.practice_test_pack_id:
            n += 1
        if self.module_id:
            n += 1
        if self.practice_test_id or self.practice_test_ids:
            n += 1
        # File / link deliverable counts as one slot.
        if self.attachment_file or self.external_url:
            n += 1
        else:
            try:
                if self.extra_attachments.exists():
                    n += 1
            except Exception:
                pass
        try:
            if self.assessment_homework is not None:
                n += 1
        except Exception:
            pass
        return n

    @property
    def is_multi_content(self) -> bool:
        """A 'bundle': several contents attached at once (e.g. a file + a past paper + an
        assessment). Bundles are instructional — students open each resource and each
        auto-graded part still records its own score in its own engine, but the classroom
        assignment is NOT auto-finalized into one combined grade (graded manually)."""
        return self.content_count >= 2

    @property
    def is_auto_graded(self) -> bool:
        """Auto-graded = objective work (practice tests, past papers, mock exams, module
        tests, quizzes/assessments). These are scored + graded automatically and never
        enter the teacher's manual grading queue. Manual = file/instructions only, OR a
        multi-content bundle (instructional — graded manually)."""
        if self.is_multi_content:
            return False
        if (
            self.mock_exam_id
            or self.practice_test_id
            or self.practice_test_pack_id
            or self.module_id
            or self.practice_test_ids
        ):
            return True
        try:
            return self.assessment_homework is not None
        except Exception:
            return False

    @property
    def auto_source_label(self) -> str:
        """Human label for the auto-grading source shown in the gradebook."""
        if self.is_multi_content:
            return "Bundle"
        if self.mock_exam_id:
            return "Mock Exam"
        if self.module_id:
            return "Module Test"
        if self.practice_test_id or self.practice_test_pack_id or self.practice_test_ids:
            return "Practice Test"
        try:
            if self.assessment_homework is not None:
                return "Quiz"
        except Exception:
            pass
        return "Manual"


class AssignmentExtraAttachment(models.Model):
    """Additional homework files beyond the primary ``Assignment.attachment_file``."""

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="extra_attachments"
    )
    file = models.FileField(upload_to="homework_files/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "class_assignment_extra_attachments"
        ordering = ["id"]


def raw_target_practice_test_ids_from_fks(
    mock_exam_id: int | None,
    practice_test_ids: list | None,
    practice_test_id: int | None,
    practice_test_pack_id: int | None = None,
) -> list[int]:
    """
    Practice test row ids before practice_scope filtering (mock, pack, bundle, or single).
    """
    if mock_exam_id:
        order = {"READING_WRITING": 0, "MATH": 1}
        rows = list(
            PracticeTest.objects.filter(mock_exam_id=mock_exam_id).values_list("id", "subject")
        )
        rows.sort(key=lambda r: (order.get(r[1], 9), r[0]))
        return [r[0] for r in rows]
    if practice_test_pack_id:
        order = {"READING_WRITING": 0, "MATH": 1}
        rows = list(
            PracticeTest.objects.filter(practice_test_pack_id=practice_test_pack_id).values_list(
                "id", "subject"
            )
        )
        rows.sort(key=lambda r: (order.get(r[1], 9), r[0]))
        return [r[0] for r in rows]
    if practice_test_ids:
        out: list[int] = []
        for x in practice_test_ids:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    if practice_test_id:
        return [practice_test_id]
    return []


def filter_practice_targets_by_scope(raw_ids: list[int], scope: str) -> list[int]:
    """Keep only Reading & Writing or Math rows when scope is not BOTH."""
    if not raw_ids or scope == Assignment.PRACTICE_SCOPE_BOTH:
        return raw_ids
    subs = dict(PracticeTest.objects.filter(id__in=raw_ids).values_list("id", "subject"))
    out: list[int] = []
    for pk in raw_ids:
        subj = subs.get(pk)
        if subj is None:
            continue
        if scope == Assignment.PRACTICE_SCOPE_ENGLISH and subj == "READING_WRITING":
            out.append(pk)
        elif scope == Assignment.PRACTICE_SCOPE_MATH and subj == "MATH":
            out.append(pk)
    return out


def assignment_target_practice_test_ids(assignment: Assignment) -> list[int]:
    """Practice test ids linked to this homework, after applying practice_scope."""
    raw = raw_target_practice_test_ids_from_fks(
        assignment.mock_exam_id,
        assignment.practice_test_ids,
        assignment.practice_test_id,
        practice_test_pack_id=getattr(assignment, "practice_test_pack_id", None),
    )
    scope = assignment.practice_scope or Assignment.PRACTICE_SCOPE_BOTH
    return filter_practice_targets_by_scope(raw, scope)


def grant_practice_test_library_access_for_assignment(assignment: Assignment) -> None:
    """
    Student /practice-tests list only includes standalone PracticeTest rows the user is in
    ``assigned_users`` for (unless they have staff library permissions). Class homework that
    targets a pastpaper card / section did not update that M2M, so assigned work was invisible
    on the global practice library until bulk-assign from admin. Sync class students here.
    Timed mock sections (mock_exam set) are skipped.
    """
    ids = assignment_target_practice_test_ids(assignment)
    if not ids:
        return
    standalone = PracticeTest.objects.filter(pk__in=ids, mock_exam__isnull=True)
    if not standalone.exists():
        return
    student_ids = list(
        assignment.classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT
        ).values_list("user_id", flat=True)
    )
    if not student_ids:
        return
    User = get_user_model()
    users = list(User.objects.filter(pk__in=student_ids))
    if not users:
        return
    for pt in standalone:
        pt.assigned_users.add(*users)


def grant_practice_test_library_access_for_user_in_classroom(classroom: Classroom, user) -> None:
    """When a student joins a class, unlock existing pastpaper homework targets on the practice library."""
    if user is None:
        return
    for assignment in Assignment.objects.filter(classroom=classroom):
        ids = assignment_target_practice_test_ids(assignment)
        if not ids:
            continue
        for pt in PracticeTest.objects.filter(pk__in=ids, mock_exam__isnull=True):
            pt.assigned_users.add(user)


class Submission(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_REVIEWED = "REVIEWED"
    STATUS_RETURNED = "RETURNED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_RETURNED, "Returned for revision"),
    ]

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)

    # Optional link to an attempt in the existing exam system
    attempt = models.ForeignKey(
        TestAttempt, on_delete=models.SET_NULL, null=True, blank=True, related_name="class_submissions"
    )

    submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Set when teacher returns work; student may edit again without extending submitted_at until resubmit.
    returned_at = models.DateTimeField(null=True, blank=True, db_index=True)
    return_note = models.TextField(blank=True, help_text="Visible to student when status is RETURNED.")
    # Monotonic counter bumped on each successful mutation (files, attempt, status, teacher actions).
    revision = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_submissions"
        unique_together = [("assignment", "student")]
        ordering = ["-submitted_at", "-updated_at"]

    def mark_submitted(self) -> None:
        """Finalize student work (draft or returned → submitted). Idempotent if already final."""
        if self.status in (self.STATUS_SUBMITTED, self.STATUS_REVIEWED):
            return
        if self.status not in (self.STATUS_DRAFT, self.STATUS_RETURNED):
            raise ValueError(f"Cannot submit from status {self.status}")
        self.status = self.STATUS_SUBMITTED
        self.submitted_at = timezone.now()
        self.returned_at = None
        self.return_note = ""


class SubmissionFile(models.Model):
    """One row per uploaded file; submissions support many files without overwriting."""

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="files"
    )
    file = models.FileField(upload_to="homework_submissions/%Y/%m/")
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=120, blank=True)
    # Idempotency: SHA-256 of stored bytes; optional per-file client token for retry dedupe.
    content_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    upload_token = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "class_submission_files"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "upload_token"),
                name="uniq_submission_file_upload_token_nonempty",
                condition=Q(upload_token__gt=""),
            ),
            models.UniqueConstraint(
                fields=("submission", "content_sha256"),
                name="uniq_submission_file_sha_nonempty",
                condition=Q(content_sha256__gt=""),
            ),
        ]

    def delete(self, using=None, keep_parents=False):
        """Remove storage file then DB row; retry storage delete to reduce orphan files."""
        from .submission_file_storage import delete_submission_file_storage, record_stale_storage_blob

        name = self.file.name if self.file else ""
        ok = delete_submission_file_storage(self.file)
        if not ok and name:
            record_stale_storage_blob(name, reason="delete_failed_after_retries")
        return super().delete(using=using, keep_parents=keep_parents)


class StaleStorageBlob(models.Model):
    """
    Storage path that could not be deleted after retries (S3/network glitch, etc.).
    Safe to delete rows after confirming the object is gone from storage.
    """

    storage_name = models.CharField(max_length=512, db_index=True)
    reason = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    alert_logged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When we emitted a CRITICAL log for this row (repeated delete failures).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "class_stale_storage_blobs"
        ordering = ["-created_at"]


class HomeworkStagedUpload(models.Model):
    """
    Tracks blob lifecycle between streaming to storage and DB attach (optional observability).

    * staging — bytes written; row not yet linked by ``SubmissionFile``
    * attached — ``SubmissionFile`` row points at ``storage_path``
    * abandoned — compensation deleted the object or duplicate skipped upload
    """

    STATUS_STAGING = "staging"
    STATUS_ATTACHED = "attached"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_STAGING, "Staging"),
        (STATUS_ATTACHED, "Attached"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    submission = models.ForeignKey(
        "Submission",
        on_delete=models.CASCADE,
        related_name="staged_uploads",
    )
    storage_path = models.CharField(max_length=512)
    upload_token = models.CharField(max_length=64, blank=True, default="")
    content_sha256 = models.CharField(max_length=64, blank=True, default="")
    deterministic = models.BooleanField(
        default=False,
        help_text="True when path was derived from a client upload_token (retry overwrites same key).",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_STAGING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_homework_staged_uploads"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "storage_path"),
                name="uniq_homework_staged_path_per_submission",
            ),
        ]


class SubmissionReview(models.Model):
    """Teacher feedback and optional score for a homework submission."""

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, related_name="review"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="given_submission_reviews",
    )
    grade = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    # Points the work was graded out of (falls back to Assignment.max_score). Without it,
    # a free-form grade can't be normalized to a percent for Academic ranking.
    max_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    # True when produced by objective auto-grading (test/assessment), not human review.
    # Auto grades never appear in the teacher's "Needs grading" queue.
    is_auto = models.BooleanField(default=False, db_index=True)
    reviewed_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "class_submission_reviews"

    def normalized_percent(self) -> float | None:
        """Grade as 0–100, using this row's max_score or the assignment's. None if not gradable."""
        if self.grade is None:
            return None
        ceiling = self.max_score
        if ceiling is None:
            ceiling = getattr(self.submission.assignment, "max_score", None)
        if not ceiling or float(ceiling) <= 0:
            return None
        pct = 100.0 * float(self.grade) / float(ceiling)
        return max(0.0, min(100.0, pct))


class SubmissionAuditEvent(models.Model):
    """Immutable event log for submission lifecycle (status, files, reviews)."""

    EVENT_STATUS_CHANGE = "status_change"
    EVENT_FILE_ADD = "file_add"
    EVENT_FILE_REMOVE = "file_remove"
    EVENT_REVIEW_UPSERT = "review_upsert"
    EVENT_RETURN = "return_for_revision"
    EVENT_ATTEMPT_CHANGE = "attempt_change"

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="audit_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submission_audit_events",
    )
    event_type = models.CharField(max_length=40, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "class_submission_audit_events"
        ordering = ["-created_at", "-id"]


def submission_workflow_status(submission: Submission | None) -> str:
    """
    UI lifecycle for classwork (aligned with ``Submission.status``).
    """
    if submission is None:
        return "NOT_STARTED"
    if submission.status == Submission.STATUS_DRAFT:
        return "NOT_STARTED"
    if submission.status == Submission.STATUS_RETURNED:
        return "RETURNED"
    if submission.status == Submission.STATUS_REVIEWED:
        return "GRADED"
    if submission.status == Submission.STATUS_SUBMITTED:
        return "SUBMITTED"
    return "NOT_STARTED"


class ClassroomStreamItem(models.Model):
    """
    Denormalized activity feed for a class (posts, new assignments, submission events).
    ``related_id`` points at ``ClassPost.id``, ``Assignment.id``, or ``Submission.id`` depending on ``stream_type``.
    """

    TYPE_POST = "post"
    TYPE_ASSIGNMENT = "assignment"
    TYPE_SUBMISSION = "submission"
    TYPE_CHOICES = [
        (TYPE_POST, "Post"),
        (TYPE_ASSIGNMENT, "Assignment"),
        (TYPE_SUBMISSION, "Submission"),
    ]

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="stream_items",
    )
    stream_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classroom_stream_actions",
    )
    related_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "classroom_stream_items"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["stream_type", "related_id"],
                name="classroom_stream_unique_type_related",
            )
        ]
        indexes = [
            models.Index(fields=["classroom", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Stream#{self.pk} {self.stream_type} in {self.classroom_id}"


class ClassComment(models.Model):
    """Threaded comments on announcements or assignments within a class."""

    TARGET_POST = "post"
    TARGET_ASSIGNMENT = "assignment"
    TARGET_CHOICES = [
        (TARGET_POST, "Post"),
        (TARGET_ASSIGNMENT, "Assignment"),
    ]

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES, db_index=True)
    target_id = models.PositiveIntegerField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField(max_length=10_000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_comments"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["classroom", "target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        return f"Comment#{self.pk} on {self.target_type}:{self.target_id}"


@receiver(post_save, sender=ClassroomMembership)
def _grant_practice_library_on_student_enroll(sender, instance, created, **kwargs):
    if not created or instance.role != ClassroomMembership.ROLE_STUDENT:
        return
    grant_practice_test_library_access_for_user_in_classroom(instance.classroom, instance.user)


# Register rebuild models (attendance, rankings, analytics) with the `classes` app.
# Defined in separate modules for clarity; imported here so migrations detect them.
from .models_attendance import AttendanceSession, AttendanceRecord  # noqa: E402,F401
from .models_ranking import (  # noqa: E402,F401
    AcademicWeightConfig,
    ClassroomRankingConfig,
    RankingSnapshot,
)
from .models_analytics import StudentGoal  # noqa: E402,F401

