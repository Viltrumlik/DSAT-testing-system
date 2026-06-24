import logging

from django.conf import settings as django_settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils import timezone
from users.models import User

from .attempt_state_machine import (
    TransitionNotAllowed,
    assert_primary_transition_allowed,
    assert_repair_transition_allowed,
)
from .engine_db_guard import TransitionConflict, conditional_attempt_update

logger = logging.getLogger(__name__)

class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Question(TimestampedModel):
    QUESTION_TYPES = [
        ('MATH', 'Math'),
        ('READING', 'Reading'),
        ('WRITING', 'Writing'),
    ]
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, db_index=True)
    question_text = models.TextField()
    question_prompt = models.TextField(blank=True, help_text="Secondary text displayed above answer choices.")
    question_image = models.ImageField(upload_to='question_images/', null=True, blank=True)
    option_a = models.TextField(blank=True)
    option_a_image = models.ImageField(upload_to='option_images/', null=True, blank=True)
    option_b = models.TextField(blank=True)
    option_b_image = models.ImageField(upload_to='option_images/', null=True, blank=True)
    option_c = models.TextField(blank=True)
    option_c_image = models.ImageField(upload_to='option_images/', null=True, blank=True)
    option_d = models.TextField(blank=True)
    option_d_image = models.ImageField(upload_to='option_images/', null=True, blank=True)
    correct_answers = models.TextField(help_text="For math input, separate multiple correct answers with a comma. e.g. '2/3, 0.666, 0.667'")
    is_math_input = models.BooleanField(default=False)
    score = models.IntegerField(default=10, help_text="Score weight for this question")
    explanation = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    module = models.ForeignKey('Module', on_delete=models.CASCADE, related_name='questions', null=True)

    # Question Bank links (M1, additive/nullable). When set, this row is a
    # per-exam frozen copy sourced from the canonical bank question; bank_version
    # pins the immutable version so a published exam stays frozen across future
    # bank edits. NULL = legacy/standalone question not yet linked to the bank.
    bank_question = models.ForeignKey(
        'questionbank.BankQuestion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exam_questions', db_index=True,
    )
    bank_version = models.ForeignKey(
        'questionbank.BankQuestionVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exam_questions',
    )

    class Meta:
        db_table = 'questions'
        ordering = ['order', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=["module", "order"],
                condition=models.Q(module__isnull=False),
                name="uniq_question_order_per_module",
            ),
        ]
    
    def __str__(self):
        return f"{self.get_question_type_display()} Q{self.id}"

    def get_options(self):
        options = {}
        if self.option_a or self.option_a_image:
            options['A'] = {'text': self.option_a, 'image': self.option_a_image.url if self.option_a_image else None}
        if self.option_b or self.option_b_image:
            options['B'] = {'text': self.option_b, 'image': self.option_b_image.url if self.option_b_image else None}
        if self.option_c or self.option_c_image:
            options['C'] = {'text': self.option_c, 'image': self.option_c_image.url if self.option_c_image else None}
        if self.option_d or self.option_d_image:
            options['D'] = {'text': self.option_d, 'image': self.option_d_image.url if self.option_d_image else None}
        return options if options else None

    _OPTION_SLOTS = (
        ("option_a", "option_a_image", "A"),
        ("option_b", "option_b_image", "B"),
        ("option_c", "option_c_image", "C"),
        ("option_d", "option_d_image", "D"),
    )

    def clean(self):
        super().clean()
        errors = {}

        if not (self.question_text or "").strip():
            errors["question_text"] = "Question text cannot be empty or whitespace-only."

        expl = self.explanation
        if expl is not None and expl != "" and not expl.strip():
            errors["explanation"] = "Explanation cannot be whitespace-only."

        filled_letters = []
        for text_f, img_f, letter in self._OPTION_SLOTS:
            raw_text = getattr(self, text_f) or ""
            stripped = raw_text.strip()
            has_img = bool(getattr(self, img_f))
            if stripped or has_img:
                filled_letters.append(letter)

        if not self.is_math_input:
            if len(filled_letters) < 2:
                errors[NON_FIELD_ERRORS] = [
                    "At least two options must have non-empty text or an image."
                ]

            ca_raw = (self.correct_answers or "").strip()
            if not ca_raw:
                errors["correct_answers"] = "Correct answer is required."
            elif len(ca_raw) != 1 or ca_raw[0].lower() not in "abcd":
                errors["correct_answers"] = (
                    "Correct answer must be a single letter A, B, C, or D."
                )
            else:
                chosen = ca_raw.upper()[0]
                if chosen not in filled_letters:
                    errors["correct_answers"] = (
                        "Correct answer must match one of the filled options (A–D)."
                    )
        else:
            self._clean_math_correct_answers(errors)

        if errors:
            raise ValidationError(errors)

    def _clean_math_correct_answers(self, errors):
        s = (self.correct_answers or "").strip()
        if not s:
            errors["correct_answers"] = "Correct answer is required for math input."
            return
        parts = [p.strip() for p in s.split(",")]
        if not parts:
            errors["correct_answers"] = "Provide at least one comma-separated answer variant."
            return
        if any(not p for p in parts):
            errors["correct_answers"] = (
                "Each comma-separated answer variant must be non-empty."
            )
            return
        for p in parts:
            if len(p) > 512:
                errors["correct_answers"] = (
                    "Each answer variant must be at most 512 characters."
                )
                return
            if any(ord(c) < 32 for c in p):
                errors["correct_answers"] = (
                    "Answer variants cannot contain control characters."
                )
                return

    def check_answer(self, student_answer):
        if student_answer is None or str(student_answer).strip() == "":
            return False
            
        student_ans_str = str(student_answer).strip().lower()
        
        if self.is_math_input and self.correct_answers:
            valid_answers = [v.strip().lower() for v in self.correct_answers.split(',')]
            return student_ans_str in valid_answers
            
        if self.correct_answers:
            return student_ans_str == self.correct_answers.strip().lower()
            
        return False

    def save(self, *args, **kwargs):
        """
        When ``module`` is set, ``order`` is assigned under a **dense** 0..n-1 contract with a
        ``Module`` row lock (see ``question_ordering.save_question_dense_locked``).

        Use ``_plain_db_save=True`` only for internal persistence after ordering is finalized.
        """
        if kwargs.pop("_plain_db_save", False):
            super().save(*args, **kwargs)
            return

        if kwargs.pop("_skip_question_order_normalize", False):
            super().save(*args, **kwargs)
            return

        from .question_ordering import save_question_dense_locked

        mid = self.module_id
        if mid is None:
            super().save(*args, **kwargs)
            return

        save_question_dense_locked(self, *args, **kwargs)

class MockExam(TimestampedModel):
    KIND_MOCK_SAT = "MOCK_SAT"
    KIND_MIDTERM = "MIDTERM"
    KIND_CHOICES = [
        (KIND_MOCK_SAT, "Full SAT mock (Reading & Writing + Math)"),
        (KIND_MIDTERM, "Midterm (custom time, 1–2 modules, one subject)"),
    ]

    title = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Timed diagnostic mock (staff-authored). Not built from pastpaper practice items.",
    )
    practice_date = models.DateField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        help_text="When True, students with portal access see this timed mock. Pastpaper practice uses separate standalone tests.",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=KIND_MOCK_SAT,
        db_index=True,
    )
    # Used when kind=MIDTERM (teacher/admin-configured)
    midterm_subject = models.CharField(
        max_length=20,
        choices=[("READING_WRITING", "Reading & Writing"), ("MATH", "Math")],
        default="READING_WRITING",
    )
    # Midterm scoring scale chosen by the admin at creation time. SCALE_100 keeps
    # the clean 0–100 percentage; SCALE_800 maps the midterm onto the SAT 200–800
    # proportional curve (using midterm_subject for the per-module caps). The
    # question console branches its scoring hints on this.
    SCALE_100 = "SCALE_100"
    SCALE_800 = "SCALE_800"
    MIDTERM_SCORING_SCALE_CHOICES = [
        (SCALE_100, "100-point (percentage)"),
        (SCALE_800, "800-point (SAT scaled)"),
    ]
    midterm_scoring_scale = models.CharField(
        max_length=20,
        choices=MIDTERM_SCORING_SCALE_CHOICES,
        default=SCALE_100,
        help_text="Only used when kind=MIDTERM. Controls the final score scale.",
    )
    midterm_module_count = models.PositiveSmallIntegerField(default=2)
    midterm_module1_minutes = models.PositiveIntegerField(default=60)
    midterm_module2_minutes = models.PositiveIntegerField(default=60)
    midterm_target_question_count = models.PositiveIntegerField(
        default=0,
        help_text="0 = no fixed target. Otherwise planner cap for total questions across modules.",
    )
    # Who may open this mock in the app (full SAT / midterm flow). Separate from PracticeTest rows below.
    assigned_users = models.ManyToManyField(
        User,
        related_name="assigned_mock_exams",
        blank=True,
        help_text="Students/teachers who see this mock on the Mock Exam page.",
    )

    class Meta:
        db_table = "mock_exams"

    def __str__(self):
        date_str = self.practice_date.strftime("%B %Y") if self.practice_date else "No Date"
        return f"{date_str} - {self.title}"


class PortalMockExam(TimestampedModel):
    """
    Student Mock Exam page only: separate table from PracticeTest.
    Until a row exists here, the portal mock list is empty. Links to MockExam for /mock/:id engine data.
    """

    mock_exam = models.OneToOneField(
        MockExam,
        on_delete=models.CASCADE,
        related_name="portal_listing",
        help_text="Underlying mock (R&W/Math sections are PracticeTest rows; not exposed on the mock list API).",
    )
    assigned_users = models.ManyToManyField(
        User,
        related_name="assigned_portal_mock_exams",
        blank=True,
        help_text="Who sees this mock on the student Mock Exam page.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "portal_mock_exams"

    def __str__(self):
        return f"Portal: {self.mock_exam}"


class PracticeTestPack(TimestampedModel):
    """
    Groups custom/user-created practice test sections (R&W + Math).
    Official old-SAT pastpapers are standalone PracticeTest sections (no pack),
    distinguished by their ``collection_name`` label.
    """

    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Practice test pack title shown in admin and student lists.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description for the practice test pack.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_practice_test_packs",
    )
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only published packs are visible to students.",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "practice_test_packs"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"PracticeTestPack {self.pk}"


class PracticeTest(TimestampedModel):
    SUBJECT_CHOICES = [
        ('READING_WRITING', 'Reading & Writing'),
        ('MATH', 'Math'),
    ]
    FORM_TYPES = [
        ('INTERNATIONAL', 'International Form'),
        ('US', 'US Form'),
    ]
    mock_exam = models.ForeignKey(
        MockExam,
        on_delete=models.CASCADE,
        related_name="tests",
        null=True,
        blank=True,
        help_text="NULL = pastpaper / practice library. If set, this row is a mock-only section (staff-built under that mock, never linked from pastpapers).",
    )
    practice_test_pack = models.ForeignKey(
        PracticeTestPack,
        on_delete=models.CASCADE,
        related_name="sections",
        null=True,
        blank=True,
        help_text="When set, this section belongs to a custom practice test pack (not a pastpaper).",
    )
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES, db_index=True)
    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Pastpaper / practice test name (shown in admin and student lists).",
    )
    practice_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional official/exam date shown on student practice cards.",
    )
    label = models.CharField(max_length=10, blank=True, help_text="e.g., A, B, C, D")
    form_type = models.CharField(max_length=20, choices=FORM_TYPES, default='INTERNATIONAL', db_index=True)
    collection_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Optional grouping label (formerly the pastpaper pack title). Lets standalone "
            "sections be distinguished/grouped in admin, builder and student lists."
        ),
    )
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Only published sections are shown to students who don't have an explicit "
            "assignment. Section-level replacement for the old pack publish gate."
        ),
    )
    published_at = models.DateTimeField(null=True, blank=True)
    assigned_users = models.ManyToManyField(User, related_name='assigned_tests', blank=True)
    skip_default_modules = models.BooleanField(
        default=False,
        help_text="If True, post_save does not auto-create SAT modules (midterm/custom builds).",
    )

    class Meta:
        db_table = 'practice_tests'

    def clean(self):
        super().clean()
        s = getattr(self, "subject", None)
        if s not in ("MATH", "READING_WRITING"):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"subject": "PracticeTest.subject must be MATH or READING_WRITING."}
            )

    def has_questions_for_attempts(self) -> bool:
        """At least one ``Question`` under some ``Module`` — required to start a ``TestAttempt``."""
        if not self.pk:
            return False
        return Question.objects.filter(module__practice_test_id=self.pk).exists()

    def modules_exist_without_questions(self) -> bool:
        """
        Invalid configuration for attempts: module rows exist but no questions were authored.
        Distinct from 'no modules yet' during draft creation.
        """
        if not self.pk:
            return False
        if not self.modules.exists():
            return False
        return not self.has_questions_for_attempts()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk and self.modules_exist_without_questions():
            logger.warning(
                "PracticeTest id=%s has modules but no questions; not usable for student attempts.",
                self.pk,
            )

    def __str__(self):
        if self.mock_exam:
            exam_title = self.mock_exam.title
        elif self.collection_name:
            exam_title = self.collection_name
        elif self.title:
            exam_title = self.title
        else:
            exam_title = "Unassigned"
        label_str = f" ({self.label})" if self.label else ""
        return f"{exam_title} - {self.get_subject_display()}{label_str} [{self.get_form_type_display()}]"

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=PracticeTest)
def create_default_modules(sender, instance, created, **kwargs):
    if not created or instance.skip_default_modules:
        return
    from .sat_rules import SAT_MODULE_TIME_LIMIT_MINUTES
    minutes = SAT_MODULE_TIME_LIMIT_MINUTES.get(instance.subject, 35)
    Module.objects.create(
        practice_test=instance,
        module_order=1,
        time_limit_minutes=minutes,
    )
    Module.objects.create(
        practice_test=instance,
        module_order=2,
        time_limit_minutes=minutes,
    )

class Module(TimestampedModel):
    practice_test = models.ForeignKey(PracticeTest, on_delete=models.CASCADE, related_name='modules')
    MODULE_ORDERS = [(1, 'Module 1'), (2, 'Module 2')]
    module_order = models.IntegerField(choices=MODULE_ORDERS, db_index=True)
    time_limit_minutes = models.IntegerField()
    question_order_high_water = models.BigIntegerField(
        default=0,
        help_text="Monotonic high-water mark for Question.order allocations (avoids Max(order) hotspot).",
    )
    
    class Meta:
        db_table = 'modules'
        ordering = ['practice_test', 'module_order']
        constraints = [
            models.UniqueConstraint(
                fields=["practice_test", "module_order"],
                name="uniq_module_order_per_test",
            ),
            models.CheckConstraint(
                condition=models.Q(module_order__in=[1, 2]),
                name="chk_module_order_1_2",
            ),
            models.CheckConstraint(
                condition=models.Q(time_limit_minutes__gt=0),
                name="chk_module_time_limit_positive",
            ),
        ]

    def __str__(self):
        exam_title = (
            self.practice_test.mock_exam.title
            if self.practice_test and self.practice_test.mock_exam
            else "Unassigned"
        )
        return f"{exam_title} - {self.practice_test.get_subject_display()} - Mod {self.module_order}"


def ensure_full_mock_practice_test_modules(practice_test: PracticeTest) -> None:
    """
    Guarantee required timed modules exist for the exam engine.

    - Full SAT mock sections (non-midterm): always require Module 1 + Module 2.
    - Midterms: require Module 1; Module 2 only when mock.midterm_module_count >= 2.

    NOTE: Historically, midterms/custom builds used ``skip_default_modules=True`` to avoid the
    post_save auto-provision. However, the exam runner assumes the required module rows exist
    when transitioning Module 1 → Module 2. If a required Module 2 row is missing (deleted or
    mis-provisioned), the attempt can transition into MODULE_2_ACTIVE with no current_module,
    leaving the frontend stuck. This helper is the single defensive backstop to prevent that.
    """
    if practice_test.subject not in ("READING_WRITING", "MATH"):
        return

    mock = getattr(practice_test, "mock_exam", None)
    kind = getattr(mock, "kind", None) if mock else None

    # Determine which module orders should exist.
    required_orders: tuple[int, ...] = (1, 2)
    if kind == MockExam.KIND_MIDTERM:
        cnt = int(getattr(mock, "midterm_module_count", 2) or 2)
        required_orders = (1, 2) if cnt >= 2 else (1,)

    existing_orders = set(practice_test.modules.values_list("module_order", flat=True))

    def _default_minutes() -> int:
        from .sat_rules import SAT_MODULE_TIME_LIMIT_MINUTES
        return SAT_MODULE_TIME_LIMIT_MINUTES.get(practice_test.subject, 35)

    for order in required_orders:
        if order in existing_orders:
            continue
        if kind == MockExam.KIND_MIDTERM and mock:
            if order == 1:
                mins = int(getattr(mock, "midterm_module1_minutes", 60) or 60)
            else:
                mins = int(getattr(mock, "midterm_module2_minutes", 60) or 60)
        else:
            mins = _default_minutes()

        try:
            Module.objects.get_or_create(
                practice_test=practice_test,
                module_order=order,
                defaults={"time_limit_minutes": max(1, mins)},
            )
        except IntegrityError:
            # Concurrent provisioning race: another request created the row.
            pass


class TestAttempt(TimestampedModel):
    practice_test = models.ForeignKey(PracticeTest, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='test_attempts')
    # Tracks which MockExam this section attempt belongs to (set when the section's
    # PracticeTest is part of a MOCK_SAT or MIDTERM). Used for cross-section ordering
    # enforcement, break enforcement, and aggregated exam-level scoring.
    mock_exam = models.ForeignKey(
        "MockExam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="section_attempts",
    )
    
    # Legacy timestamps (kept for backward compatibility with existing clients/admin views).
    started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    current_module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True)
    # Legacy (kept): corresponds to whichever module is active.
    current_module_start_time = models.DateTimeField(null=True, blank=True)
    
    completed_modules = models.ManyToManyField(Module, related_name='completed_attempts', blank=True)
    
    module_answers = models.JSONField(default=dict, blank=True)
    flagged_questions = models.JSONField(default=dict, blank=True)
    
    # ── Exam engine state machine (backend-authoritative) ────────────────────
    STATE_NOT_STARTED = "NOT_STARTED"
    STATE_MODULE_1_ACTIVE = "MODULE_1_ACTIVE"
    STATE_MODULE_1_SUBMITTED = "MODULE_1_SUBMITTED"
    STATE_MODULE_2_ACTIVE = "MODULE_2_ACTIVE"
    STATE_MODULE_2_SUBMITTED = "MODULE_2_SUBMITTED"
    STATE_SCORING = "SCORING"
    STATE_COMPLETED = "COMPLETED"
    STATE_ABANDONED = "ABANDONED"
    STATE_CHOICES = [
        (STATE_NOT_STARTED, "Not started"),
        (STATE_MODULE_1_ACTIVE, "Module 1 active"),
        (STATE_MODULE_1_SUBMITTED, "Module 1 submitted"),
        (STATE_MODULE_2_ACTIVE, "Module 2 active"),
        (STATE_MODULE_2_SUBMITTED, "Module 2 submitted"),
        (STATE_SCORING, "Scoring"),
        (STATE_COMPLETED, "Completed"),
        (STATE_ABANDONED, "Abandoned"),
    ]
    # NB: kept as a CharField so we can evolve the state machine without DB enum churn.
    current_state = models.CharField(
        max_length=24,
        choices=STATE_CHOICES,
        default=STATE_NOT_STARTED,
        db_index=True,
    )

    # Per-module timestamps (server authoritative for timers/resume)
    module_1_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    module_1_submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    module_2_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    module_2_submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Pause bookkeeping — total seconds spent paused while in each module, plus
    # the timestamp the current pause started (null when not paused). The
    # deadline check subtracts these from elapsed time so a student who pauses
    # to take a break doesn't have the timer keep counting against them.
    module_1_paused_seconds = models.PositiveIntegerField(default=0)
    module_2_paused_seconds = models.PositiveIntegerField(default=0)
    pause_started_at = models.DateTimeField(null=True, blank=True)
    scoring_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    abandoned_checkpoint_state = models.CharField(
        max_length=24,
        blank=True,
        default="",
        null=True,
        help_text=(
            "Snapshot of current_state persisted when transitioning to ABANDONED "
            "(authoritative resume target; empty/null => restart module 1)."
        ),
    )

    # Optimistic concurrency: bumped on every successful state mutation (start/autosave/submit/score).
    version_number = models.PositiveIntegerField(default=0, db_index=True)

    is_completed = models.BooleanField(default=False, db_index=True)
    score = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'test_attempts'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=["student", "practice_test"],
                condition=models.Q(is_completed=False) & ~models.Q(current_state="ABANDONED"),
                name="uniq_active_attempt_per_student_test",
            )
        ]

    def __str__(self):
        return f"{self.student.email} - {self.practice_test}"

    def _module_by_order(self, order: int) -> Module | None:
        try:
            order = int(order)
        except (TypeError, ValueError):
            return None
        return self.practice_test.modules.filter(module_order=order).order_by("id").first()

    def _set_active_module(self, module: Module) -> None:
        """
        Point at the runner module row. Anchors timers on first-seen-at server time only;
        repeats / pointer healing must not rewind ``current_module_start_time``.
        """
        now = timezone.now()
        self.current_module = module
        order = int(getattr(module, "module_order", 0) or 0)
        if order == 1:
            self.module_1_started_at = self.module_1_started_at or now
            self.current_module_start_time = self.module_1_started_at
        elif order == 2:
            self.module_2_started_at = self.module_2_started_at or now
            self.current_module_start_time = self.module_2_started_at

    def _assert_invariants(self) -> None:
        """
        Internal safety checks. Do not call on every read; call after mutations.
        """
        st = self.current_state
        cm = self.current_module
        cm_order = getattr(cm, "module_order", None) if cm else None

        if st == self.STATE_MODULE_1_ACTIVE and cm_order != 1:
            raise ValidationError("Invariant violation: MODULE_1_ACTIVE requires current_module.order=1")
        if st == self.STATE_MODULE_2_ACTIVE and cm_order != 2:
            raise ValidationError("Invariant violation: MODULE_2_ACTIVE requires current_module.order=2")
        if st in (self.STATE_SCORING, self.STATE_COMPLETED, self.STATE_ABANDONED) and cm is not None:
            raise ValidationError("Invariant violation: scoring/completed/abandoned must have current_module=null")
        if self.is_completed and st != self.STATE_COMPLETED:
            raise ValidationError("Invariant violation: is_completed requires current_state=COMPLETED")

    def _attempt_engine_log(self, event: str, *, from_state: str | None = None, detail: str = "") -> None:
        """Minimal structured logging for attempt lifecycle (state + module pointer)."""
        mo = getattr(self.current_module, "module_order", None) if self.current_module_id else None
        logger.info(
            "exam_attempt_transition attempt_id=%s event=%s from_state=%s to_state=%s "
            "current_module_id=%s module_order=%s v=%s %s",
            self.id,
            event,
            from_state or "",
            self.current_state,
            self.current_module_id,
            mo,
            self.version_number,
            detail.strip(),
        )
        if getattr(django_settings, "EXAM_ENGINE_AUDIT_DB", True):
            try:
                AttemptEngineAudit.objects.create(
                    attempt_id=int(self.pk),
                    event=str(event),
                    from_state=str(from_state or "")[:64],
                    to_state=str(self.current_state)[:64],
                    version_number=int(self.version_number or 0),
                    detail=(detail or "")[:4000],
                )
            except Exception:
                logger.exception("exam_attempt_audit_persist_failed attempt_id=%s event=%s", self.id, event)

    # ── New authoritative state-machine API ──────────────────────────────────
    def start_attempt(self) -> None:
        """
        Start or resume the attempt. Must be called under select_for_update().
        Behavior:
        - If NOT_STARTED: moves to MODULE_1_ACTIVE and returns module 1 as current_module.
        - If already active/submitted/scoring/completed: no-op (resume semantics).
        """
        if self.is_completed or self.current_state == self.STATE_COMPLETED:
            return
        # ABANDONED is recoverable; treat as resumable (business rule).
        if self.current_state == self.STATE_ABANDONED:
            ensure_full_mock_practice_test_modules(self.practice_test)
            raw_ck = str(getattr(self, "abandoned_checkpoint_state", "") or "").strip()
            restored: str
            if not raw_ck or raw_ck == self.STATE_NOT_STARTED:
                restored = self.STATE_MODULE_1_ACTIVE
            elif raw_ck == self.STATE_MODULE_1_ACTIVE:
                restored = self.STATE_MODULE_1_ACTIVE
            elif raw_ck == self.STATE_MODULE_2_ACTIVE:
                restored = self.STATE_MODULE_2_ACTIVE
            elif raw_ck == self.STATE_SCORING:
                restored = self.STATE_SCORING
            elif raw_ck == self.STATE_MODULE_1_SUBMITTED:
                restored = self.STATE_MODULE_2_ACTIVE
            elif raw_ck == self.STATE_MODULE_2_SUBMITTED:
                restored = self.STATE_SCORING
            else:
                restored = self.STATE_MODULE_1_ACTIVE
            assert_repair_transition_allowed(self.STATE_ABANDONED, restored)
            from_state = self.current_state
            if restored == self.STATE_SCORING:
                now = timezone.now()
                self.scoring_started_at = self.scoring_started_at or now
                self.current_state = self.STATE_SCORING
                self.current_module = None
                self.current_module_start_time = None
            elif restored == self.STATE_MODULE_1_ACTIVE:
                m1 = self._module_by_order(1)
                if not m1:
                    raise ValidationError("Module 1 is missing.")
                self.current_state = self.STATE_MODULE_1_ACTIVE
                self._set_active_module(m1)
            else:
                m2 = self._module_by_order(2)
                if not m2:
                    raise ValidationError("Module 2 is missing.")
                self.current_state = self.STATE_MODULE_2_ACTIVE
                self._set_active_module(m2)
            self.version_number = int(self.version_number or 0) + 1
            upd = [
                "current_state",
                "current_module",
                "current_module_start_time",
                "module_1_started_at",
                "module_2_started_at",
                "scoring_started_at",
                "version_number",
                "updated_at",
            ]
            if self.started_at is None:
                self.started_at = timezone.now()
                upd.insert(0, "started_at")
            self.save(update_fields=upd)
            self._assert_invariants()
            self._attempt_engine_log(
                "start_attempt",
                from_state=from_state,
                detail=f"abandoned_resume_target={restored} checkpoint_was={raw_ck or 'EMPTY'}",
            )
            return

        ensure_full_mock_practice_test_modules(self.practice_test)
        if not self.started_at:
            self.started_at = timezone.now()

        if self.current_state == self.STATE_NOT_STARTED:
            m1 = self._module_by_order(1)
            if not m1:
                raise ValidationError("Module 1 is missing.")
            from_state = self.current_state
            assert_primary_transition_allowed(from_state, self.STATE_MODULE_1_ACTIVE)
            ts = timezone.now()
            v0 = int(self.version_number or 0)
            new_v = v0 + 1
            started_val = self.started_at or ts
            m1_start = self.module_1_started_at or ts
            n = conditional_attempt_update(
                pk=int(self.pk),
                expect_state=self.STATE_NOT_STARTED,
                expect_version=v0,
                updates={
                    "started_at": started_val,
                    "current_state": self.STATE_MODULE_1_ACTIVE,
                    "current_module_id": int(m1.pk),
                    "current_module_start_time": m1_start,
                    "module_1_started_at": m1_start,
                    "version_number": new_v,
                    "updated_at": ts,
                },
            )
            if n == 0:
                self.refresh_from_db()
                if self.current_state == self.STATE_MODULE_1_ACTIVE:
                    return
                raise TransitionConflict("start_attempt(NOT_STARTED) concurrent transition")
            self.refresh_from_db()
            self._assert_invariants()
            self._attempt_engine_log("start_attempt", from_state=from_state)
            return

        # Resume: ensure current_module pointer is consistent with state.
        if self.current_state in (self.STATE_MODULE_1_ACTIVE, self.STATE_MODULE_2_ACTIVE) and not self.current_module:
            desired = 1 if self.current_state == self.STATE_MODULE_1_ACTIVE else 2
            m = self._module_by_order(desired)
            if not m:
                raise ValidationError(f"Module {desired} is missing.")
            from_state = self.current_state
            self._set_active_module(m)
            self.version_number = int(self.version_number or 0) + 1
            self.save(
                update_fields=[
                    "current_module",
                    "current_module_start_time",
                    "module_1_started_at",
                    "module_2_started_at",
                    "version_number",
                    "updated_at",
                ]
            )
            self._assert_invariants()
            self._attempt_engine_log("start_attempt", from_state=from_state)

    def submit_module_1(self, module_answers: dict, flagged: list | None = None) -> bool:
        """
        MODULE_1_ACTIVE → MODULE_2_ACTIVE in one persisted step (never leaves *_SUBMITTED on disk).
        Must be called under select_for_update().
        Returns True if transition ran; False if already advanced (duplicate submit/idempotent noop).
        """
        from_state = self.current_state
        if self.current_state == self.STATE_MODULE_2_ACTIVE:
            mod = getattr(self, "current_module", None)
            if mod is not None and getattr(mod, "module_order", None) == 2:
                return False
            raise TransitionNotAllowed(
                "Idempotent mismatch: MODULE_2_ACTIVE without valid current_module order 2."
            )
        if self.current_state != self.STATE_MODULE_1_ACTIVE:
            raise ValidationError(f"Cannot submit module 1 from state {self.current_state}")
        if not self.current_module or getattr(self.current_module, "module_order", None) != 1:
            raise ValidationError("Current module is not module 1.")

        # Save answers/flags for current module
        mod = self.current_module
        mid = int(mod.id)
        self.module_answers = self.module_answers or {}
        self.flagged_questions = self.flagged_questions or {}
        self.module_answers[str(mid)] = module_answers or {}
        self.flagged_questions[str(mid)] = flagged or []

        # Idempotency by completed_modules
        if not self.completed_modules.filter(pk=mid).exists():
            self.completed_modules.add(mod)

        now = timezone.now()
        self.module_1_submitted_at = self.module_1_submitted_at or now

        # Immediately advance to module 2 (no persisted MODULE_1_SUBMITTED).
        ensure_full_mock_practice_test_modules(self.practice_test)
        m2 = self._module_by_order(2)

        # Single-module exams skip straight to SCORING instead of advancing to a Module 2:
        #   - a single-module MIDTERM (midterm_module_count == 1) has NO Module 2 row, and
        #   - a single-module pastpaper has a Module 2 row with zero questions.
        # Either way there is no second module to take, so finalize for scoring.
        single_module = (m2 is None) or (m2.questions.count() == 0)
        if single_module:
            assert_primary_transition_allowed(self.STATE_MODULE_1_ACTIVE, self.STATE_SCORING)
            ts = timezone.now()
            v0 = int(self.version_number or 0)
            new_v = v0 + 1
            m1_sub = self.module_1_submitted_at or ts
            # Mark M2 timestamps so scoring pipeline sees a complete attempt
            m2_sub = ts
            scoring_at = ts
            if m2 is not None and not self.completed_modules.filter(pk=m2.pk).exists():
                self.completed_modules.add(m2)
            n = conditional_attempt_update(
                pk=int(self.pk),
                expect_state=self.STATE_MODULE_1_ACTIVE,
                expect_version=v0,
                updates={
                    "module_answers": self.module_answers,
                    "flagged_questions": self.flagged_questions,
                    "current_state": self.STATE_SCORING,
                    "module_1_submitted_at": m1_sub,
                    "module_2_submitted_at": m2_sub,
                    "module_2_started_at": m2_sub,
                    "scoring_started_at": scoring_at,
                    "current_module_id": None,
                    "current_module_start_time": None,
                    "version_number": new_v,
                    "updated_at": ts,
                },
            )
            if n == 0:
                self.refresh_from_db()
                if self.current_state == self.STATE_SCORING:
                    return False
                raise TransitionConflict("submit_module_1 (empty m2 shortcut) concurrent state drift")
            self.refresh_from_db()
            self._assert_invariants()
            self._attempt_engine_log(
                "submit_module_1",
                from_state=from_state,
                detail="single_module_skip_to_scoring" if m2 is None else "module_2_empty_skip_to_scoring",
            )
            return True

        assert_primary_transition_allowed(self.STATE_MODULE_1_ACTIVE, self.STATE_MODULE_2_ACTIVE)
        ts = timezone.now()
        v0 = int(self.version_number or 0)
        new_v = v0 + 1
        m1_sub = self.module_1_submitted_at or ts
        m2_anchor = self.module_2_started_at or ts
        n = conditional_attempt_update(
            pk=int(self.pk),
            expect_state=self.STATE_MODULE_1_ACTIVE,
            expect_version=v0,
            updates={
                "module_answers": self.module_answers,
                "flagged_questions": self.flagged_questions,
                "current_state": self.STATE_MODULE_2_ACTIVE,
                "module_1_submitted_at": m1_sub,
                "current_module_id": int(m2.pk),
                "current_module_start_time": m2_anchor,
                "module_2_started_at": m2_anchor,
                "version_number": new_v,
                "updated_at": ts,
            },
        )
        if n == 0:
            self.refresh_from_db()
            if (
                self.current_state == self.STATE_MODULE_2_ACTIVE
                and self.current_module_id == int(m2.pk)
            ):
                return False
            raise TransitionConflict("submit_module_1 concurrent state drift")
        self.refresh_from_db()
        self._assert_invariants()
        self._attempt_engine_log(
            "submit_module_1",
            from_state=from_state,
            detail="module_2_started",
        )
        return True

    def submit_module_2(self, module_answers: dict, flagged: list | None = None) -> bool:
        """
        MODULE_2_ACTIVE → SCORING in one persisted step (no MODULE_2_SUBMITTED on disk).
        Must be called under select_for_update().
        Returns True if transition ran; False if already in SCORING (idempotent duplicate submit).
        """
        from_state = self.current_state
        if self.current_state == self.STATE_SCORING:
            return False
        if self.current_state != self.STATE_MODULE_2_ACTIVE:
            raise ValidationError(f"Cannot submit module 2 from state {self.current_state}")
        if not self.current_module or getattr(self.current_module, "module_order", None) != 2:
            raise ValidationError("Current module is not module 2.")

        mod = self.current_module
        mid = int(mod.id)
        self.module_answers = self.module_answers or {}
        self.flagged_questions = self.flagged_questions or {}
        self.module_answers[str(mid)] = module_answers or {}
        self.flagged_questions[str(mid)] = flagged or []
        if not self.completed_modules.filter(pk=mid).exists():
            self.completed_modules.add(mod)

        now = timezone.now()
        self.module_2_submitted_at = self.module_2_submitted_at or now
        self.scoring_started_at = self.scoring_started_at or now
        assert_primary_transition_allowed(self.STATE_MODULE_2_ACTIVE, self.STATE_SCORING)
        ts = timezone.now()
        v0 = int(self.version_number or 0)
        new_v = v0 + 1
        m2_sub = self.module_2_submitted_at or ts
        scoring_at = self.scoring_started_at or ts
        n = conditional_attempt_update(
            pk=int(self.pk),
            expect_state=self.STATE_MODULE_2_ACTIVE,
            expect_version=v0,
            updates={
                "module_answers": self.module_answers,
                "flagged_questions": self.flagged_questions,
                "module_2_submitted_at": m2_sub,
                "scoring_started_at": scoring_at,
                "current_state": self.STATE_SCORING,
                "current_module_id": None,
                "current_module_start_time": None,
                "version_number": new_v,
                "updated_at": ts,
            },
        )
        if n == 0:
            self.refresh_from_db()
            if self.current_state == self.STATE_SCORING:
                return False
            raise TransitionConflict("submit_module_2 concurrent state drift")
        self.refresh_from_db()
        self._assert_invariants()
        self._attempt_engine_log(
            "submit_module_2",
            from_state=from_state,
            detail=("scoring_enqueued_candidate" if scoring_at else ""),
        )
        return True

    def repair_legacy_submitted_states(self) -> None:
        """
        Management / repair tooling only — folds persisted MODULE_*_SUBMITTED into active/SCORING.
        Must be called under select_for_update().
        HTTP clients must NOT rely on this; use ``python manage.py repair_exam_integrity``.
        """
        # First: pointer healing + canonical start only (no *_SUBMITTED repair).
        self.start_attempt()

        if self.current_state == self.STATE_MODULE_1_SUBMITTED:
            ensure_full_mock_practice_test_modules(self.practice_test)
            m2 = self._module_by_order(2)
            if not m2:
                raise ValidationError("Module 2 is missing; cannot resume.")
            from_state = self.current_state
            assert_repair_transition_allowed(from_state, self.STATE_MODULE_2_ACTIVE)
            self.current_state = self.STATE_MODULE_2_ACTIVE
            self._set_active_module(m2)
            self.version_number = int(self.version_number or 0) + 1
            self.save(
                update_fields=[
                    "current_state",
                    "current_module",
                    "current_module_start_time",
                    "module_2_started_at",
                    "version_number",
                    "updated_at",
                ]
            )
            self._assert_invariants()
            self._attempt_engine_log("repair_legacy_submit", from_state=from_state, detail="module1_submitted_legacy")
            return

        if self.current_state == self.STATE_MODULE_2_SUBMITTED:
            # If module-2 was submitted but scoring wasn't entered, move to SCORING.
            now = timezone.now()
            from_state = self.current_state
            assert_repair_transition_allowed(from_state, self.STATE_SCORING)
            self.scoring_started_at = self.scoring_started_at or now
            self.current_state = self.STATE_SCORING
            self.current_module = None
            self.current_module_start_time = None
            self.version_number = int(self.version_number or 0) + 1
            self.save(
                update_fields=[
                    "current_state",
                    "scoring_started_at",
                    "current_module",
                    "current_module_start_time",
                    "version_number",
                    "updated_at",
                ]
            )
            self._assert_invariants()
            self._attempt_engine_log(
                "repair_legacy_submit",
                from_state=from_state,
                detail="module2_submitted_legacy_to_scoring",
            )
            return

    def complete_attempt(self) -> None:
        """
        SCORING → COMPLETED. Called by scoring worker under select_for_update().
        """
        if self.current_state == self.STATE_COMPLETED and self.is_completed:
            return
        if self.current_state != self.STATE_SCORING:
            raise ValidationError(f"Cannot complete attempt from state {self.current_state}")
        from_state = self.current_state
        self.complete_test()
        self._assert_invariants()
        self._attempt_engine_log(
            "complete_attempt",
            from_state=from_state,
            detail=f"is_completed={'1' if self.is_completed else '0'}",
        )

    def start_module(self, module: Module) -> None:
        """
        Narrow legacy hook: advancing timed sections happens via submit/start_attempt.
        - Module 1: only ``NOT_STARTED`` → ``MODULE_1_ACTIVE``.
        - Module 2: only idempotent reaffirm while already ``MODULE_2_ACTIVE`` with the same module row.
        """
        if self.is_completed or self.current_state == self.STATE_COMPLETED:
            raise ValidationError("Cannot start module for a completed test")
        if not module or module.practice_test_id != self.practice_test_id:
            raise ValidationError("Invalid module for this attempt")

        if not self.started_at:
            self.started_at = timezone.now()

        if module.module_order == 1:
            if self.current_state != self.STATE_NOT_STARTED:
                raise ValidationError(
                    f"Cannot start module 1 via start_module from state {self.current_state}; use POST .../start/."
                )
            from_state = self.current_state
            assert_primary_transition_allowed(from_state, self.STATE_MODULE_1_ACTIVE)
            self.current_state = self.STATE_MODULE_1_ACTIVE
            self._set_active_module(module)
            self.version_number = int(self.version_number or 0) + 1
            self.save(
                update_fields=[
                    "started_at",
                    "current_state",
                    "current_module",
                    "current_module_start_time",
                    "module_1_started_at",
                    "version_number",
                    "updated_at",
                ]
            )
            self._assert_invariants()
            self._attempt_engine_log("start_module", from_state=from_state, detail=f"target_order={module.module_order}")
            return

        if module.module_order == 2:
            if self.current_state != self.STATE_MODULE_2_ACTIVE:
                raise ValidationError(
                    "Module 2 is opened only after the server advances from module 1 (submit). "
                    f"Got state {self.current_state}."
                )
            if self.current_module_id != module.pk:
                raise TransitionNotAllowed("MODULE_2_ACTIVE but current_module does not match requested module.")
            return

        raise ValidationError("Invalid module order")

    def complete_test(self):
        if self.is_completed:
            return
        if self.current_state != self.STATE_SCORING:
            raise ValidationError(f"Cannot finalize attempt scoring from state {self.current_state}")
        assert_primary_transition_allowed(self.STATE_SCORING, self.STATE_COMPLETED)

        now = timezone.now()
        v0 = int(self.version_number or 0)
        new_v = v0 + 1
        submitted_val = self.submitted_at or now
        completed_val = self.completed_at or now

        pt = self.practice_test
        mock = getattr(pt, "mock_exam", None)
        if mock is None and pt.mock_exam_id:
            mock = MockExam.objects.filter(pk=pt.mock_exam_id).first()

        # Pastpapers and standalone practice-test packs use raw-points scoring
        # (sum of per-question scores for correctly answered questions). The
        # SAT 200-base + 800-cap curve is reserved for mock exams that the
        # teacher explicitly assembles as a full SAT simulation.
        # Any non-mock section (standalone pastpaper or practice-test pack) uses
        # raw-points scoring; mock exams use the proportional SAT curve below.
        is_pastpaper_or_practice = pt.mock_exam_id is None

        if mock and mock.kind == MockExam.KIND_MIDTERM:
            scale = getattr(mock, "midterm_scoring_scale", MockExam.SCALE_100)
            if scale == MockExam.SCALE_800:
                # 800-point scale: map the midterm onto the SAT 200-base + per-module
                # cap proportional curve, using the midterm's configured subject for
                # the caps. Mirrors the full-SAT path but for a single subject.
                from .sat_rules import compute_sat_module_score
                subject = getattr(mock, "midterm_subject", None) or self.practice_test.subject
                earned = 0
                for module_id_str, answers in self.module_answers.items():
                    try:
                        module = Module.objects.prefetch_related("questions").get(id=int(module_id_str))
                    except (ValueError, Module.DoesNotExist):
                        continue
                    correct_pts = 0
                    total_pts = 0
                    for question in module.questions.all():
                        q_score = int(question.score or 0)
                        total_pts += q_score
                        ans = answers.get(str(question.id))
                        if question.check_answer(ans):
                            correct_pts += q_score
                    earned += compute_sat_module_score(
                        earned_points=correct_pts,
                        total_possible_points=total_pts,
                        subject=subject,
                        module_order=module.module_order,
                    )
                score_val = min(200 + earned, 800)
            else:
                # 100-point scale: (correct answers / total questions) × 100.
                # Each question counts equally regardless of its stored score weight,
                # so the final result is always a clean 0–100 percentage.
                correct_count = 0
                total_count = 0
                for module_id_str, answers in self.module_answers.items():
                    try:
                        module = Module.objects.prefetch_related("questions").get(id=int(module_id_str))
                    except (ValueError, Module.DoesNotExist):
                        continue
                    for question in module.questions.all():
                        total_count += 1
                        ans = answers.get(str(question.id))
                        if question.check_answer(ans):
                            correct_count += 1
                score_val = round((correct_count / total_count) * 100) if total_count > 0 else 0
        elif is_pastpaper_or_practice:
            # Pastpapers / practice tests: 200 floor + raw per-question score
            # for each correctly answered question. No 800 ceiling and no
            # proportional curve — students keep the full points they earned.
            # The 200 floor mirrors the SAT minimum so a perfect-zero attempt
            # still reads as a SAT-like number instead of "0".
            total_earned = 0
            for module_id_str, answers in self.module_answers.items():
                try:
                    module = Module.objects.prefetch_related("questions").get(id=int(module_id_str))
                except (ValueError, Module.DoesNotExist):
                    continue
                for question in module.questions.all():
                    ans = answers.get(str(question.id))
                    if question.check_answer(ans):
                        total_earned += int(question.score or 0)
            score_val = 200 + total_earned
        else:
            # ── SAT Section Scoring (Proportional) ──────────────────────────
            # Official Digital SAT score architecture:
            #   Reading & Writing: base 200, M1 contributes up to 330 (→ 530),
            #                      M2 contributes up to 270 (→ 800 total)
            #   Math:              base 200, M1 contributes up to 380 (→ 580),
            #                      M2 contributes up to 220 (→ 800 total)
            #
            # Scoring is PROPORTIONAL:
            #   module_contribution = round((correct_pts / total_pts) × module_cap)
            # This guarantees a perfect module always reaches its cap regardless
            # of whether individual question scores are 10, 20, or 40.
            from .sat_rules import compute_sat_module_score
            subject = self.practice_test.subject
            m1_earned = 0
            m2_earned = 0

            for module_id_str, answers in self.module_answers.items():
                try:
                    module = Module.objects.prefetch_related("questions").get(id=int(module_id_str))
                    correct_pts = 0
                    total_pts = 0
                    for question in module.questions.all():
                        q_score = int(question.score or 0)
                        total_pts += q_score
                        ans = answers.get(str(question.id))
                        if question.check_answer(ans):
                            correct_pts += q_score

                    contrib = compute_sat_module_score(
                        earned_points=correct_pts,
                        total_possible_points=total_pts,
                        subject=subject,
                        module_order=module.module_order,
                    )
                    if module.module_order == 1:
                        m1_earned = contrib
                    elif module.module_order == 2:
                        m2_earned = contrib
                except Module.DoesNotExist:
                    import logging as _logging
                    _logging.getLogger(__name__).error(
                        "complete_test: module %s not found for attempt %s — scoring anomaly",
                        module_id_str,
                        self.pk,
                    )
                except Exception as _exc:  # noqa: BLE001
                    import logging as _logging
                    _logging.getLogger(__name__).exception(
                        "complete_test: unexpected error scoring module %s for attempt %s: %s",
                        module_id_str,
                        self.pk,
                        _exc,
                    )

            score_val = min(200 + m1_earned + m2_earned, 800)

        n = conditional_attempt_update(
            pk=int(self.pk),
            expect_state=self.STATE_SCORING,
            expect_version=v0,
            updates={
                "submitted_at": submitted_val,
                "is_completed": True,
                "current_state": self.STATE_COMPLETED,
                "completed_at": completed_val,
                "version_number": new_v,
                "score": int(score_val),
                "current_module_id": None,
                "updated_at": now,
            },
        )
        if n == 0:
            self.refresh_from_db()
            if self.is_completed:
                return
            raise TransitionConflict("complete_test concurrent state drift")
        self.refresh_from_db()

    def get_module_results(self):
        """
        Returns detailed results broken down by module for the review page.

        For SAT section scoring, ``capped_earned`` uses the same proportional
        formula as ``complete_test()`` — so the review page always matches
        the stored score exactly.

        Fields added to each module result:
          module_earned  — raw weighted score (sum of correct question.score values)
          total_possible — sum of ALL question.score values in this module
          capped_earned  — proportional SAT contribution (or raw for midterms)
          module_cap     — the maximum this module can contribute (0 for midterms)
        """
        from .sat_rules import compute_sat_module_score
        results = []
        subject = self.practice_test.subject
        pt = self.practice_test
        mock = getattr(pt, "mock_exam", None)
        if mock is None and pt.mock_exam_id:
            mock = MockExam.objects.filter(pk=pt.mock_exam_id).first()
        is_midterm = bool(mock and mock.kind == MockExam.KIND_MIDTERM)
        # Pastpapers and standalone practice-test packs use raw-points scoring
        # (no SAT 200-base / 800-cap curve). The review page should mirror that.
        # Any non-mock section (standalone pastpaper or practice-test pack) uses
        # raw-points scoring; mock exams use the proportional SAT curve below.
        is_pastpaper_or_practice = pt.mock_exam_id is None

        modules = self.practice_test.modules.prefetch_related('questions').order_by('module_order')

        for module in modules:
            module_answers = self.module_answers.get(str(module.id), {})
            questions_data = []
            correct_pts = 0
            total_pts = 0

            for question in module.questions.all():
                student_ans = module_answers.get(str(question.id))
                is_correct = question.check_answer(student_ans)
                q_score = int(question.score or 0)
                total_pts += q_score
                if is_correct:
                    correct_pts += q_score

                questions_data.append({
                    'id': question.id,
                    'is_correct': is_correct,
                    'student_answer': student_ans,
                    'correct_answers': question.correct_answers,
                    'score': q_score,
                    'text': question.question_text,
                    'question_prompt': question.question_prompt,
                    'image': question.question_image.url if question.question_image else None,
                    'type': question.get_question_type_display(),
                    'options': question.get_options(),
                    'is_math_input': question.is_math_input
                })

            if is_midterm or is_pastpaper_or_practice:
                # Midterms / pastpapers / practice tests: raw weighted sum,
                # no proportional SAT mapping or 200-base curve.
                capped_earned = correct_pts
                module_cap = 0
            else:
                # SAT: proportional — same formula as complete_test()
                capped_earned = compute_sat_module_score(
                    earned_points=correct_pts,
                    total_possible_points=total_pts,
                    subject=subject,
                    module_order=module.module_order,
                )
                from .sat_rules import SAT_MODULE_SCORE_CAP
                module_cap = SAT_MODULE_SCORE_CAP.get(subject, {}).get(module.module_order, 0)

            results.append({
                'module_id': module.id,
                'module_order': module.module_order,
                'module_earned': correct_pts,   # raw weighted correct score
                'total_possible': total_pts,     # raw weighted total possible
                'capped_earned': capped_earned,  # proportional SAT contribution
                'module_cap': module_cap,        # max this module can contribute
                'questions': questions_data
            })

        return results

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"


class BulkAssignmentDispatch(models.Model):
    """
    Audit trail for ``/api/exams/bulk_assign/`` library dispatches (pastpaper sections + timed mocks).

    ``payload`` stores the exact request body subset for ``rerun``; ``result`` stores structured outcome.
    """

    KIND_PASTPAPER = "pastpaper"
    KIND_TIMED_MOCK = "timed_mock"
    KIND_MIXED = "mixed"
    KIND_CHOICES = [
        (KIND_PASTPAPER, "Pastpaper library"),
        (KIND_TIMED_MOCK, "Timed mock"),
        (KIND_MIXED, "Mixed"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DELIVERED = "delivered"  # kept for legacy rows; new code uses COMPLETED/FAILED
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bulk_library_dispatches",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    subject_summary = models.CharField(max_length=200, blank=True, default="")
    students_requested_count = models.PositiveIntegerField(default=0)
    students_granted_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    actor_snapshot = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=64, blank=True, db_index=True)
    idempotency_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    rerun_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reruns",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "exams_bulk_assignment_dispatch"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"BulkDispatch#{self.pk} {self.kind} by {self.assigned_by_id}"


class AttemptIdempotencyKey(models.Model):
    """
    Stores responses for idempotent attempt mutations (submit/autosave/start).
    """

    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name="idempotency_keys")
    endpoint = models.CharField(max_length=64, db_index=True)
    key = models.CharField(max_length=128, db_index=True)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "exams_attempt_idempotency_keys"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "endpoint", "key"], name="uniq_attempt_endpoint_key"),
        ]


class AttemptEngineAudit(models.Model):
    """Append-only record of authoritative exam-engine transitions for debugging and forensic replay."""

    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name="engine_audits")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.CharField(max_length=64, db_index=True)
    from_state = models.CharField(max_length=64, blank=True)
    to_state = models.CharField(max_length=64)
    version_number = models.PositiveIntegerField(default=0)
    detail = models.TextField(blank=True)

    class Meta:
        db_table = "exams_attempt_engine_audit"
        indexes = [
            models.Index(fields=["attempt", "created_at"]),
        ]
