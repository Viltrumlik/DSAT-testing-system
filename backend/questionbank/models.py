"""
Question Bank — the single source of truth for all SAT questions.

M0 (this milestone) ships these models INERT: no other app references them yet,
no API is exposed, and no existing data is migrated. Consumers (exams,
assessments) gain nullable links in M1. Nothing here modifies an existing table.

Design invariants:
  - QB-ID is permanent and never reused (see qb_id.py).
  - BankPassage stores R&W stimulus text once; many questions reference it.
  - BankQuestion holds the live, editable state; BankQuestionVersion is an
    append-only immutable snapshot per edit (governance mirrors
    assessments.AssessmentSetVersion).
  - UNCLASSIFIED == NULL domain/skill + status=TRIAGE. We do NOT create sentinel
    "Unclassified" taxonomy rows, so analytics filter cleanly on
    (status=APPROVED, domain__isnull=False).
  - source_type / source_reference / import_batch preserve provenance.
  - content_hash powers duplicate detection (flag, never block).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


# ──────────────────────────────────────────────────────────────────────────────
# Shared choice vocabularies
# ──────────────────────────────────────────────────────────────────────────────
class Subject(models.TextChoices):
    ENGLISH = "ENGLISH", "English"
    MATH = "MATH", "Math"


class Difficulty(models.TextChoices):
    EASY = "EASY", "Easy"
    MEDIUM = "MEDIUM", "Medium"
    HARD = "HARD", "Hard"


class QuestionType(models.TextChoices):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Multiple choice"
    STUDENT_PRODUCED = "STUDENT_PRODUCED", "Student-produced response (grid-in)"
    SHORT_TEXT = "SHORT_TEXT", "Short text"
    NUMERIC = "NUMERIC", "Numeric"
    BOOLEAN = "BOOLEAN", "True/False"


class QuestionStatus(models.TextChoices):
    """Master gate. Only APPROVED questions are selectable by consumers and
    counted in analytics."""
    IMPORTED = "IMPORTED", "Imported (raw)"
    TRIAGE = "TRIAGE", "In triage (awaiting classification)"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    ARCHIVED = "ARCHIVED", "Archived"


class SourceType(models.TextChoices):
    MANUAL = "MANUAL", "Manually authored"
    PDF_IMPORT = "PDF_IMPORT", "PDF import"
    MIGRATED_EXAM = "MIGRATED_EXAM", "Migrated from exam engine"
    MIGRATED_ASSESSMENT = "MIGRATED_ASSESSMENT", "Migrated from assessments"
    COLLEGE_BOARD = "COLLEGE_BOARD", "College Board"
    OTHER = "OTHER", "Other"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ──────────────────────────────────────────────────────────────────────────────
# Taxonomy
# ──────────────────────────────────────────────────────────────────────────────
class BankDomain(models.Model):
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=64, help_text="Stable machine code, e.g. 'algebra'.")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "qb_domains"
        ordering = ["subject", "display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["subject", "name"], name="uniq_qb_domain_subject_name"),
            models.UniqueConstraint(fields=["subject", "code"], name="uniq_qb_domain_subject_code"),
        ]

    def __str__(self) -> str:
        return f"{self.get_subject_display()} › {self.name}"


class BankSkill(models.Model):
    domain = models.ForeignKey(BankDomain, on_delete=models.PROTECT, related_name="skills")
    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=64, help_text="Stable machine code, e.g. 'linear-functions'.")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "qb_skills"
        ordering = ["domain", "display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["domain", "name"], name="uniq_qb_skill_domain_name"),
            models.UniqueConstraint(fields=["domain", "code"], name="uniq_qb_skill_domain_code"),
        ]

    def __str__(self) -> str:
        return f"{self.domain.name} › {self.name}"


# ──────────────────────────────────────────────────────────────────────────────
# ID allocation
# ──────────────────────────────────────────────────────────────────────────────
class QbIdCounter(models.Model):
    """One monotonic counter row per subject. See qb_id.allocate_qb_id."""
    subject = models.CharField(max_length=16, choices=Subject.choices, primary_key=True)
    last_value = models.BigIntegerField(default=0)

    class Meta:
        db_table = "qb_id_counters"

    def __str__(self) -> str:
        return f"{self.subject}: {self.last_value}"


# ──────────────────────────────────────────────────────────────────────────────
# Import provenance
# ──────────────────────────────────────────────────────────────────────────────
class ImportBatch(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARSING = "PARSING", "Parsing"
        READY = "READY", "Ready for review"
        PROMOTED = "PROMOTED", "Promoted to bank"
        FAILED = "FAILED", "Failed"

    source_type = models.CharField(max_length=32, choices=SourceType.choices, default=SourceType.PDF_IMPORT)
    filename = models.CharField(max_length=512, blank=True, default="")
    source_reference = models.CharField(
        max_length=512, blank=True, default="",
        help_text="Free-form origin pointer (URL, original document id, etc.).",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="question_import_batches",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    total_candidates = models.PositiveIntegerField(default=0)
    promoted_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "qb_import_batches"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"ImportBatch #{self.pk} ({self.source_type}, {self.status})"


# ──────────────────────────────────────────────────────────────────────────────
# Passage normalization — text stored once, many questions reference it
# ──────────────────────────────────────────────────────────────────────────────
class BankPassage(TimestampedModel):
    subject = models.CharField(max_length=16, choices=Subject.choices, default=Subject.ENGLISH, db_index=True)
    passage_text = models.TextField()
    content_hash = models.CharField(max_length=64, db_index=True, blank=True, default="")

    source_type = models.CharField(max_length=32, choices=SourceType.choices, default=SourceType.MANUAL)
    source_reference = models.CharField(max_length=512, blank=True, default="")
    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="passages",
    )
    metadata = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = "qb_passages"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["subject", "content_hash"])]

    def __str__(self) -> str:
        preview = (self.passage_text or "").strip().replace("\n", " ")[:60]
        return f"Passage #{self.pk}: {preview}…"


# ──────────────────────────────────────────────────────────────────────────────
# Canonical question — live editable state + status gate
# ──────────────────────────────────────────────────────────────────────────────
class BankQuestionQuerySet(models.QuerySet):
    def approved(self):
        """Questions eligible for consumers AND analytics: APPROVED with real
        (non-UNCLASSIFIED) taxonomy. This is the single gate — TRIAGE / IMPORTED
        / archived / unclassified rows are never selectable or counted."""
        return self.filter(
            status=QuestionStatus.APPROVED,
            domain__isnull=False,
            skill__isnull=False,
        )

    def in_triage(self):
        return self.filter(status__in=[QuestionStatus.IMPORTED, QuestionStatus.TRIAGE])


class BankQuestion(TimestampedModel):
    objects = BankQuestionQuerySet.as_manager()

    qb_id = models.CharField(
        max_length=32, unique=True, editable=False, db_index=True,
        help_text="Permanent identifier, e.g. QB-ENG-000001. Assigned once, never changes.",
    )
    # Official source identifier (e.g. College Board question ID) carried in from
    # the PDF. Unique ACROSS questions when set (a cross-question collision is a
    # duplicate); preserved across the version chain and through publish. Blank is
    # allowed (manually authored questions) and exempt from the uniqueness rule.
    external_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)

    # Taxonomy — NULL = UNCLASSIFIED (triage). Never auto-filled.
    domain = models.ForeignKey(
        BankDomain, on_delete=models.PROTECT, null=True, blank=True, related_name="questions",
    )
    skill = models.ForeignKey(
        BankSkill, on_delete=models.PROTECT, null=True, blank=True, related_name="questions",
    )
    difficulty = models.CharField(max_length=8, choices=Difficulty.choices, blank=True, default="", db_index=True)

    status = models.CharField(
        max_length=16, choices=QuestionStatus.choices, default=QuestionStatus.IMPORTED, db_index=True,
    )
    question_type = models.CharField(max_length=32, choices=QuestionType.choices, db_index=True)

    # Content -----------------------------------------------------------------
    passage = models.ForeignKey(
        BankPassage, on_delete=models.PROTECT, null=True, blank=True, related_name="questions",
    )
    question_text = models.TextField()
    question_prompt = models.TextField(blank=True, default="", help_text="Secondary text above the choices.")
    question_image = models.ImageField(upload_to="question_bank/questions/", null=True, blank=True)
    option_a = models.TextField(blank=True, default="")
    option_b = models.TextField(blank=True, default="")
    option_c = models.TextField(blank=True, default="")
    option_d = models.TextField(blank=True, default="")
    option_a_image = models.ImageField(upload_to="question_bank/options/", null=True, blank=True)
    option_b_image = models.ImageField(upload_to="question_bank/options/", null=True, blank=True)
    option_c_image = models.ImageField(upload_to="question_bank/options/", null=True, blank=True)
    option_d_image = models.ImageField(upload_to="question_bank/options/", null=True, blank=True)
    # JSON to cover single letter, list of math variants, numeric, or boolean.
    correct_answer = models.JSONField(blank=True, default=None, null=True)
    # The answer a STUDENT gave in the source material (PDFs may carry both
    # "Student Answer: A" and "Correct Answer: B"). Kept SEPARATE so it can never
    # overwrite the authoritative correct_answer.
    student_answer = models.JSONField(blank=True, default=None, null=True)
    explanation = models.TextField(blank=True, default="")
    points = models.PositiveIntegerField(default=1)

    # Duplicate detection (flag, never block) ---------------------------------
    content_hash = models.CharField(max_length=64, db_index=True, blank=True, default="")

    # Provenance --------------------------------------------------------------
    source_type = models.CharField(max_length=32, choices=SourceType.choices, default=SourceType.MANUAL, db_index=True)
    source_reference = models.CharField(max_length=512, blank=True, default="")
    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions",
    )

    # AI-assisted triage suggestions — ADVISORY ONLY, never auto-applied ------
    suggested_domain = models.ForeignKey(
        BankDomain, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggested_for_questions",
    )
    suggested_skill = models.ForeignKey(
        BankSkill, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggested_for_questions",
    )
    suggested_difficulty = models.CharField(max_length=8, choices=Difficulty.choices, blank=True, default="")
    suggestion_confidence = models.FloatField(null=True, blank=True)
    suggestion_model = models.CharField(max_length=128, blank=True, default="")
    suggestion_rationale = models.TextField(blank=True, default="")

    current_version = models.ForeignKey(
        "BankQuestionVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="authored_bank_questions",
    )
    metadata = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = "qb_questions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["subject", "status"]),
            models.Index(fields=["status", "domain", "skill"]),
            models.Index(fields=["content_hash"]),
        ]
        constraints = [
            # external_id is unique across questions WHEN SET; blank is exempt so
            # manually authored questions (no source id) don't collide.
            models.UniqueConstraint(
                fields=["external_id"],
                condition=Q(external_id__gt=""),
                name="uniq_qb_external_id_when_set",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.qb_id} [{self.status}]"


# ──────────────────────────────────────────────────────────────────────────────
# Versioning — append-only, immutable, lineage-linked
# ──────────────────────────────────────────────────────────────────────────────
class BankQuestionVersion(models.Model):
    """
    Immutable snapshot of a BankQuestion at one point in time. Consumers pin
    (bank_question, version_number) at publish so published content is frozen.

    Governance (mirrors assessments.AssessmentSetVersion):
      - append-only: save() rejects mutation of an existing row,
      - undeletable: delete() raises,
      - lineage via previous_version (PROTECT),
      - snapshot_json is self-sufficient for rendering/grading.
    """
    bank_question = models.ForeignKey(BankQuestion, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField(db_index=True)
    snapshot_json = models.JSONField()
    snapshot_checksum = models.CharField(max_length=64, db_index=True)
    previous_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="successor_versions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="created_bank_question_versions",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "qb_question_versions"
        ordering = ["bank_question_id", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank_question", "version_number"], name="uniq_qb_question_version_number",
            ),
        ]

    def save(self, *args, **kwargs):  # type: ignore[override]
        if self.pk is not None:
            raise ValueError(
                "BankQuestionVersion records are immutable. Create a new version instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[override]
        raise ValueError("BankQuestionVersion records are permanent and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.bank_question_id} v{self.version_number}"


# ──────────────────────────────────────────────────────────────────────────────
# PDF import staging — parsed-but-not-yet-promoted candidates
# ──────────────────────────────────────────────────────────────────────────────
class BankQuestionAttempt(models.Model):
    """One student practice attempt at an APPROVED bank question (self-study)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_question_attempts"
    )
    bank_question = models.ForeignKey(
        BankQuestion, on_delete=models.CASCADE, related_name="attempts"
    )
    selected_answer = models.CharField(max_length=255, blank=True, default="")
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "qb_question_attempts"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.bank_question_id} · {'✓' if self.is_correct else '✗'}"


class ImportCandidate(TimestampedModel):
    """
    One parsed question awaiting human review before it becomes a BankQuestion.
    Holds the raw parse plus a validation verdict; nothing here is live content.
    """
    class Validation(models.TextChoices):
        VALID = "VALID", "Valid"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"
        DUPLICATE = "DUPLICATE", "Duplicate"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="candidates")
    order = models.PositiveIntegerField(default=0)

    # Parsed payload (mirrors the bank content fields; taxonomy is best-effort text
    # from the PDF header and is NEVER auto-applied — it is a hint for triage).
    subject = models.CharField(max_length=16, choices=Subject.choices, blank=True, default="")
    external_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    raw_domain = models.CharField(max_length=255, blank=True, default="")
    raw_skill = models.CharField(max_length=255, blank=True, default="")
    raw_difficulty = models.CharField(max_length=64, blank=True, default="")
    passage_text = models.TextField(blank=True, default="")
    question_text = models.TextField(blank=True, default="")
    option_a = models.TextField(blank=True, default="")
    option_b = models.TextField(blank=True, default="")
    option_c = models.TextField(blank=True, default="")
    option_d = models.TextField(blank=True, default="")
    correct_answer = models.JSONField(blank=True, default=None, null=True)
    student_answer = models.JSONField(blank=True, default=None, null=True)
    # Storage name of an image extracted from the PDF for this candidate
    # (best-effort, page-level association). Copied to the bank question on promote.
    question_image = models.CharField(max_length=512, blank=True, default="")
    explanation = models.TextField(blank=True, default="")

    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)

    validation_status = models.CharField(
        max_length=16, choices=Validation.choices, default=Validation.VALID, db_index=True,
    )
    validation_messages = models.JSONField(blank=True, default=list)
    duplicate_of = models.ForeignKey(
        BankQuestion, on_delete=models.SET_NULL, null=True, blank=True, related_name="import_duplicates",
    )
    promoted_question = models.ForeignKey(
        BankQuestion, on_delete=models.SET_NULL, null=True, blank=True, related_name="promoted_from_candidates",
    )

    class Meta:
        db_table = "qb_import_candidates"
        ordering = ["batch_id", "order", "id"]
        indexes = [models.Index(fields=["batch", "validation_status"])]

    def __str__(self) -> str:
        return f"Candidate #{self.pk} (batch {self.batch_id}, {self.validation_status})"
