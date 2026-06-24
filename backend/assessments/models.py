from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AssessmentSet(models.Model):
    SUBJECT_MATH = "math"
    SUBJECT_ENGLISH = "english"
    SUBJECT_CHOICES = [
        (SUBJECT_MATH, "Math"),
        (SUBJECT_ENGLISH, "English"),
    ]

    subject = models.CharField(max_length=16, choices=SUBJECT_CHOICES, db_index=True)
    category = models.CharField(max_length=255, db_index=True, blank=True, default="")
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_sets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "assessment_sets"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["subject", "category", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject}:{self.title}"


class AssessmentSetVersion(models.Model):
    """
    Immutable snapshot of an AssessmentSet at a specific point in time.

    GOVERNANCE INVARIANTS:
      INV-S01  Records are append-only. save() raises if called on an existing PK.
      INV-S02  Records cannot be deleted. delete() raises unconditionally.
      INV-S03  (assessment_set, snapshot_checksum) unique constraint prevents
               duplicate versions for identical content.
      INV-S04  snapshot_json is self-sufficient: zero dependency on live
               AssessmentQuestion rows after snapshot creation.
      INV-S05  All FKs pointing here use on_delete=PROTECT — no cascading
               deletion can silently remove historical academic records.

    ROLLBACK SAFETY:
      The nullable set_version FKs on HomeworkAssignment and AssessmentAttempt
      default to NULL so pre-snapshot workers and old deploys continue working
      with the live-lookup fallback path. No impossible rollback state.

    SNAPSHOT SCHEMA VERSION:
      Check snapshot_json["schema_version"] before parsing. Currently 1.
      Bump SNAPSHOT_SCHEMA_VERSION in snapshot_builder.py on breaking changes.
    """

    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.PROTECT,   # Cannot delete a set that has published versions
        related_name="versions",
    )
    version_number = models.PositiveIntegerField(db_index=True)

    # The immutable content payload — self-sufficient for rendering and grading.
    snapshot_json = models.JSONField()

    # SHA-256 of canonical JSON — used for integrity verification and idempotency.
    snapshot_checksum = models.CharField(max_length=64, db_index=True)

    # Denormalised question count for fast display without parsing snapshot_json.
    question_count = models.PositiveIntegerField(default=0)

    # ── Lineage chain ─────────────────────────────────────────────────────────
    # Self-referential FK to the immediately preceding version.
    # NULL for the first version of a set (no predecessor).
    # Enables: supersession graph, "what changed between v3 and v4?",
    # "which versions succeeded this one?", ancestry walks.
    #
    # GOVERNANCE: this FK uses PROTECT — deleting a version that is
    # referenced as a predecessor is not allowed (the chain is permanent).
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="successor_versions",
        help_text="The immediately preceding published version (null = first version).",
    )

    # Audit trail
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_assessment_versions",
        null=True,    # null = system-generated backfill, not a human publish action
        blank=True,
    )
    published_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "assessment_set_versions"
        ordering = ["-published_at", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment_set", "version_number"],
                name="uniq_set_version_number",
            ),
            models.UniqueConstraint(
                fields=["assessment_set", "snapshot_checksum"],
                name="uniq_set_version_checksum",
            ),
        ]
        # No extra Meta.indexes needed:
        # - (assessment_set, version_number) is covered by uniq_set_version_number constraint
        # - (assessment_set, snapshot_checksum) is covered by uniq_set_version_checksum constraint
        # - published_at index is on the field (db_index=True)

    # ── Immutability guards ───────────────────────────────────────────────────

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        """IMMUTABILITY GUARD: reject any mutation of an existing version row."""
        if self.pk is not None:
            raise ValueError(
                "AssessmentSetVersion records are immutable. "
                "Do not modify published versions — create a new version instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[override]
        """IMMUTABILITY GUARD: permanent academic records cannot be deleted."""
        raise ValueError(
            "AssessmentSetVersion records are permanent academic records "
            "and cannot be deleted."
        )

    def __str__(self) -> str:
        return f"SetVersion(set={self.assessment_set_id} v{self.version_number})"


class AssessmentQuestion(models.Model):
    TYPE_MULTIPLE_CHOICE = "multiple_choice"
    TYPE_SHORT_TEXT = "short_text"
    TYPE_NUMERIC = "numeric"
    TYPE_BOOLEAN = "boolean"
    TYPE_CHOICES = [
        (TYPE_MULTIPLE_CHOICE, "Multiple choice"),
        (TYPE_SHORT_TEXT, "Short text"),
        (TYPE_NUMERIC, "Numeric"),
        (TYPE_BOOLEAN, "True/False"),
    ]

    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    order = models.PositiveIntegerField(default=0, db_index=True)
    prompt = models.TextField()
    question_prompt = models.TextField(blank=True, default="")  # Stimulus / passage excerpt
    question_type = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)

    # For multiple choice: [{ "id": "A", "text": "..." }, ...]
    choices = models.JSONField(blank=True, default=list)

    # Correct answer can be a string/number/bool, or list of acceptable strings.
    correct_answer = models.JSONField(blank=True, default=None, null=True)
    grading_config = models.JSONField(blank=True, default=dict)  # e.g. tolerance for numeric

    points = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    # Optional image for the question stem
    question_image = models.ImageField(upload_to="assessment_questions/", blank=True, null=True)
    # Optional images for answer choices (A–D, fixed like pastpaper)
    option_a_image = models.ImageField(upload_to="assessment_questions/", blank=True, null=True)
    option_b_image = models.ImageField(upload_to="assessment_questions/", blank=True, null=True)
    option_c_image = models.ImageField(upload_to="assessment_questions/", blank=True, null=True)
    option_d_image = models.ImageField(upload_to="assessment_questions/", blank=True, null=True)
    # Solution explanation shown to students after grading
    explanation = models.TextField(blank=True, default="")

    # Question Bank links (M1, additive/nullable). bank_version pins the immutable
    # bank version this row was sourced from. Published assessments already freeze
    # via AssessmentSetVersion snapshots; these links add bank provenance/reuse
    # without changing snapshot semantics. NULL = not yet linked to the bank.
    bank_question = models.ForeignKey(
        "questionbank.BankQuestion", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assessment_questions", db_index=True,
    )
    bank_version = models.ForeignKey(
        "questionbank.BankQuestionVersion", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assessment_questions",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "assessment_questions"
        ordering = ["assessment_set_id", "order", "id"]
        indexes = [
            models.Index(fields=["assessment_set", "order"]),
        ]


class HomeworkAssignment(models.Model):
    """
    Teacher assigns an AssessmentSet as homework.

    Integrates with existing class homework feed via a linked `classes.Assignment` row.

    VERSION PINNING (Phase 1 — nullable rollout):
      set_version is NULL for assignments created before snapshot architecture.
      New assignments (post-publish endpoint) will have set_version populated.
      Grading and bundle delivery check set_version first; if NULL they fall
      back to the live question lookup path (backward compatibility).

      Phase 2: backfill existing assignments; make non-nullable.
    """

    classroom = models.ForeignKey(
        "classes.Classroom",
        on_delete=models.CASCADE,
        related_name="assessment_homework",
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.PROTECT,
        related_name="homework_assignments",
    )
    # Phase 1: nullable — old assignments have no version pin yet.
    # Phase 2 (post-backfill): add non-null constraint.
    set_version = models.ForeignKey(
        AssessmentSetVersion,
        on_delete=models.PROTECT,   # Cannot delete a version with live assignments
        related_name="homework_assignments",
        null=True,
        blank=True,
        db_index=True,
    )
    assignment = models.OneToOneField(
        "classes.Assignment",
        on_delete=models.CASCADE,
        related_name="assessment_homework",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_homework_assigned",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assessment_homework_assignments"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["classroom", "assignment"], name="uniq_assessment_hw_class_assignment"),
            models.UniqueConstraint(
                fields=["classroom", "assessment_set"],
                name="uniq_assessment_hw_classroom_set",
            ),
        ]


class AssessmentHomeworkAuditEvent(models.Model):
    EVENT_ASSIGNED = "assigned"

    EVENT_CHOICES = [
        (EVENT_ASSIGNED, "Assigned"),
    ]

    classroom = models.ForeignKey(
        "classes.Classroom",
        on_delete=models.CASCADE,
        related_name="assessment_homework_audit_events",
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.PROTECT,
        related_name="homework_audit_events",
    )
    homework = models.ForeignKey(
        HomeworkAssignment,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessment_homework_audit_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assessment_homework_audit_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["classroom", "created_at"]),
            models.Index(fields=["assessment_set", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]


class SecurityAlert(models.Model):
    """
    Durable record of security/ops alerts for post-incident analysis and webhook replay.
    """

    SOURCE_HOMEWORK_ABUSE = "homework_abuse"
    SOURCE_HOMEWORK_ABUSE_DB = "homework_abuse_db"
    SOURCE_SLO = "slo"
    SOURCE_CHOICES = [
        (SOURCE_HOMEWORK_ABUSE, "Homework abuse"),
        (SOURCE_HOMEWORK_ABUSE_DB, "Homework abuse (DB)"),
        (SOURCE_SLO, "SLO"),
    ]

    alert_type = models.CharField(max_length=80, db_index=True)
    source = models.CharField(max_length=40, db_index=True, choices=SOURCE_CHOICES, default=SOURCE_HOMEWORK_ABUSE)
    fingerprint = models.CharField(max_length=512, db_index=True, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    mitigation = models.JSONField(null=True, blank=True)
    webhook_delivered = models.BooleanField(default=False)
    email_delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assessment_security_alerts"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["alert_type", "created_at"]),
            models.Index(fields=["source", "created_at"]),
        ]


# NOTE: module-level constants so constraints can reference them safely
# during class construction (Meta is evaluated before the class name exists).
ASSESSMENT_ATTEMPT_STATUS_IN_PROGRESS = "in_progress"
ASSESSMENT_ATTEMPT_STATUS_SUBMITTED = "submitted"
ASSESSMENT_ATTEMPT_STATUS_GRADED = "graded"
ASSESSMENT_ATTEMPT_STATUS_ABANDONED = "abandoned"


class AssessmentAttempt(models.Model):
    STATUS_IN_PROGRESS = ASSESSMENT_ATTEMPT_STATUS_IN_PROGRESS
    STATUS_SUBMITTED = ASSESSMENT_ATTEMPT_STATUS_SUBMITTED
    STATUS_GRADED = ASSESSMENT_ATTEMPT_STATUS_GRADED
    STATUS_ABANDONED = ASSESSMENT_ATTEMPT_STATUS_ABANDONED
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_GRADED, "Graded"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    homework = models.ForeignKey(
        HomeworkAssignment,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assessment_attempts",
    )
    # Phase 1: nullable — old attempts have no version pin yet.
    # Grading and review read from this when present; fall back to live lookup
    # when NULL. Phase 2 (post-backfill): add non-null constraint.
    set_version = models.ForeignKey(
        AssessmentSetVersion,
        on_delete=models.PROTECT,   # Cannot delete a version with historical attempts
        related_name="attempts",
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    abandoned_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)
    total_time_seconds = models.PositiveIntegerField(default=0)
    active_time_seconds = models.PositiveIntegerField(default=0)
    # Per-question time spent, keyed by question_id (string). Recorded by the
    # student runner at submit so the result page can show a time breakdown.
    question_times = models.JSONField(blank=True, default=dict)
    # Async grading status
    GRADING_PENDING = "pending"
    GRADING_PROCESSING = "processing"
    GRADING_COMPLETED = "completed"
    GRADING_FAILED = "failed"
    GRADING_STATUS_CHOICES = [
        (GRADING_PENDING, "Pending"),
        (GRADING_PROCESSING, "Processing"),
        (GRADING_COMPLETED, "Completed"),
        (GRADING_FAILED, "Failed"),
    ]
    grading_status = models.CharField(
        max_length=24,
        choices=GRADING_STATUS_CHOICES,
        default=GRADING_PENDING,
        db_index=True,
    )
    grading_attempts = models.PositiveIntegerField(default=0)
    grading_error = models.TextField(blank=True, default="")
    grading_last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Stable question shuffle per attempt (list of AssessmentQuestion ids).
    question_order = models.JSONField(blank=True, default=list)

    class Meta:
        db_table = "assessment_attempts"
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["homework", "student"],
                condition=models.Q(status=ASSESSMENT_ATTEMPT_STATUS_IN_PROGRESS),
                name="uniq_active_attempt_per_hw_student_in_progress",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "homework", "status"]),
            models.Index(fields=["student", "status", "started_at"]),
        ]

    def lock_reason(self) -> str | None:
        if self.status in (self.STATUS_SUBMITTED, self.STATUS_GRADED):
            return "submitted"
        if self.status == self.STATUS_ABANDONED:
            return "abandoned"
        return None


class AssessmentAttemptAuditEvent(models.Model):
    EVENT_STARTED = "started"
    EVENT_ANSWER_SAVED = "answer_saved"
    EVENT_SUBMITTED = "submitted"
    EVENT_GRADED = "graded"
    EVENT_ABANDONED = "abandoned"
    EVENT_TIMEOUT_ABANDONED = "timeout_abandoned"

    EVENT_CHOICES = [
        (EVENT_STARTED, "Started"),
        (EVENT_ANSWER_SAVED, "Answer saved"),
        (EVENT_SUBMITTED, "Submitted"),
        (EVENT_GRADED, "Graded"),
        (EVENT_ABANDONED, "Abandoned"),
        (EVENT_TIMEOUT_ABANDONED, "Timeout abandoned"),
    ]

    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessment_audit_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "assessment_attempt_audit_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["attempt", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]


class AssessmentAnswer(models.Model):
    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        AssessmentQuestion,
        on_delete=models.PROTECT,
        related_name="answers",
    )
    answer = models.JSONField(blank=True, default=None, null=True)
    # Server-computed time based on first/last save timestamps (do not trust client).
    time_spent_seconds = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_correct = models.BooleanField(null=True, blank=True, db_index=True)
    points_awarded = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Client-provided monotonic sequence for conflict detection (multi-tab / out-of-order protection).
    client_seq = models.BigIntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "assessment_answers"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="uniq_answer_per_attempt_question"),
        ]


class AssessmentResult(models.Model):
    attempt = models.OneToOneField(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="result",
    )
    score_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    correct_count = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    graded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "assessment_results"
        ordering = ["-graded_at", "-id"]


class AssessmentAttemptFeedback(models.Model):
    """
    Lightweight instructional feedback written by a teacher on a student's
    assessment attempt.

    One feedback record per attempt — teachers may update it in place (this is
    not a discussion thread; it is a single instructional note per submission).

    Intentionally minimal:
    - No threading, no reactions, no mentions.
    - Read by students after submission via the pedagogical review bundle.
    - Written by teachers via the ops intervention panel.
    """

    attempt = models.OneToOneField(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="teacher_feedback",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assessment_feedbacks_given",
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_attempt_feedback"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Feedback on attempt #{self.attempt_id} by {self.teacher_id}"


class GovernanceEvent(models.Model):
    """
    Immutable, append-only audit event store for all governance actions.

    GOVERNANCE INVARIANTS:
      INV-GE01  Records are append-only. save() raises if called on an existing PK.
      INV-GE02  Records cannot be deleted — permanent audit trail.
      INV-GE03  All significant state transitions MUST emit a GovernanceEvent.
                Silent state changes are an audit violation.
      INV-GE04  actor_email is denormalized at write-time for audit stability
                — the email remains correct even if the user account is later
                modified or deleted.

    ENTITY REFERENCE (polymorphic — entity_type + entity_id):
      entity_type: Django model class name ("AssessmentSet", "AssessmentSetVersion",
                   "HomeworkAssignment", "AssessmentAttempt").
      entity_id:   Primary key of the entity.

    QUERYING:
      - Operator timeline for a set:
            GovernanceEvent.objects.filter(entity_type="AssessmentSet", entity_id=42)
      - All publish events:
            GovernanceEvent.objects.filter(event_type=GovernanceEvent.EVENT_PUBLISH)
      - Fallback usage (sunset monitoring):
            GovernanceEvent.objects.filter(event_type=GovernanceEvent.EVENT_FALLBACK_PATH_USED)
    """

    # ── Event taxonomy ─────────────────────────────────────────────────────────

    # Content lifecycle
    EVENT_PUBLISH = "publish"
    EVENT_PUBLISH_IDEMPOTENT = "publish_idempotent"      # Re-publish with identical content
    EVENT_PUBLISH_VALIDATION_FAILED = "publish_validation_failed"
    EVENT_SUPERSEDE = "supersede"                        # New version supersedes old

    # Assignment lifecycle
    EVENT_ASSIGNMENT_PIN = "assignment_pin"              # Version pinned to HomeworkAssignment

    # Attempt lifecycle
    EVENT_ATTEMPT_SNAPSHOT_PIN = "attempt_snapshot_pin" # Version pinned to AssessmentAttempt

    # Scoring
    EVENT_SCORING_START = "scoring_start"
    EVENT_SCORING_COMPLETE = "scoring_complete"
    EVENT_SCORING_RETRY = "scoring_retry"
    EVENT_SCORING_FAILURE = "scoring_failure"
    EVENT_SCORING_OVERRIDE = "scoring_override"

    # Integrity
    EVENT_INTEGRITY_FAILURE = "integrity_failure"
    EVENT_INTEGRITY_REPAIR = "integrity_repair"

    # Fallback telemetry — critical for sunset monitoring
    EVENT_FALLBACK_PATH_USED = "fallback_path_used"

    EVENT_CHOICES = [
        (EVENT_PUBLISH, "Published"),
        (EVENT_PUBLISH_IDEMPOTENT, "Publish (idempotent — identical content)"),
        (EVENT_PUBLISH_VALIDATION_FAILED, "Publish validation failed"),
        (EVENT_SUPERSEDE, "Superseded by new version"),
        (EVENT_ASSIGNMENT_PIN, "Assignment version pinned"),
        (EVENT_ATTEMPT_SNAPSHOT_PIN, "Attempt snapshot pinned"),
        (EVENT_SCORING_START, "Scoring started"),
        (EVENT_SCORING_COMPLETE, "Scoring completed"),
        (EVENT_SCORING_RETRY, "Scoring retried"),
        (EVENT_SCORING_FAILURE, "Scoring failed"),
        (EVENT_SCORING_OVERRIDE, "Scoring overridden"),
        (EVENT_INTEGRITY_FAILURE, "Integrity failure detected"),
        (EVENT_INTEGRITY_REPAIR, "Integrity repair performed"),
        (EVENT_FALLBACK_PATH_USED, "Live-read fallback path used (pre-snapshot attempt)"),
    ]

    # ── Core fields ────────────────────────────────────────────────────────────

    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES, db_index=True)

    # Polymorphic entity reference
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.BigIntegerField(db_index=True)

    # Actor attribution (nullable = system/Celery action)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="governance_events",
    )
    # Denormalized email — stable audit record independent of user lifecycle
    actor_email = models.CharField(max_length=254, blank=True, default="", db_index=True)

    # Arbitrary structured payload for operator debugging
    payload = models.JSONField(default=dict, blank=True)

    # Request trace ID linking related events across tables and log lines
    correlation_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "governance_events"
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "occurred_at"], name="gov_ev_entity_timeline_idx"),
            models.Index(fields=["event_type", "occurred_at"], name="gov_ev_type_timeline_idx"),
            models.Index(fields=["actor_email", "occurred_at"], name="gov_ev_actor_timeline_idx"),
        ]

    # ── Immutability guards ────────────────────────────────────────────────────

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if self.pk is not None:
            raise ValueError(
                "GovernanceEvent records are immutable. "
                "They are a permanent audit trail and cannot be modified."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[override]
        raise ValueError(
            "GovernanceEvent records are permanent audit records and cannot be deleted."
        )

    def __str__(self) -> str:
        return f"GovernanceEvent({self.event_type} {self.entity_type}#{self.entity_id} @{self.occurred_at})"
