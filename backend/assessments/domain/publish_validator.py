"""
PublishValidator — governance validation pipeline for AssessmentSet publish.

DESIGN:
  Validation runs BEFORE snapshot creation inside the publish transaction.

  BLOCKING findings prevent publish entirely.
  WARNING findings are recorded in the validation report and emitted as
  governance events but do NOT block publish.

  The same validator is used by:
  - AdminPublishAssessmentSetView (API enforce)
  - The pre-publish checklist page (frontend dry-run via validate endpoint)

INVARIANTS:
  INV-V01  A set cannot publish if any BLOCKING finding exists.
  INV-V02  Validation runs inside the same DB transaction as snapshot
           creation so the question set is stable (select_for_update).
  INV-V03  Validation findings are deterministic for a given (aset, questions)
           pair — no randomness, no timestamps in check logic.
  INV-V04  All future checks must be registered in _BLOCKING_CHECKS or
           _WARNING_CHECKS — never scattered across views/serializers.

EXTENSIBILITY:
  Add a new check by defining a function with signature:
      def check_name(aset, questions: list) -> list[ValidationFinding]:
  and appending it to _BLOCKING_CHECKS or _WARNING_CHECKS below.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from assessments.models import AssessmentQuestion, AssessmentSet


class ValidationSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclasses.dataclass(frozen=True)
class ValidationFinding:
    severity: ValidationSeverity
    code: str
    message: str
    question_id: int | None = None
    context: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            **({"question_id": self.question_id} if self.question_id is not None else {}),
            **({"context": self.context} if self.context else {}),
        }


@dataclasses.dataclass
class PublishValidationReport:
    findings: list[ValidationFinding]

    @property
    def is_publishable(self) -> bool:
        return not any(f.severity == ValidationSeverity.BLOCKING for f in self.findings)

    @property
    def blocking_findings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity == ValidationSeverity.BLOCKING]

    @property
    def warning_findings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity == ValidationSeverity.WARNING]

    def first_blocking_message(self) -> str | None:
        b = self.blocking_findings
        return b[0].message if b else None

    def first_blocking_code(self) -> str | None:
        b = self.blocking_findings
        return b[0].code if b else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_publishable": self.is_publishable,
            "blocking_count": len(self.blocking_findings),
            "warning_count": len(self.warning_findings),
            "findings": [f.to_dict() for f in self.findings],
        }


# ── Helper ─────────────────────────────────────────────────────────────────────


def _blocking(code: str, message: str, question_id: int | None = None, **ctx) -> ValidationFinding:
    return ValidationFinding(
        severity=ValidationSeverity.BLOCKING,
        code=code,
        message=message,
        question_id=question_id,
        context=ctx or {},
    )


def _warning(code: str, message: str, question_id: int | None = None, **ctx) -> ValidationFinding:
    return ValidationFinding(
        severity=ValidationSeverity.WARNING,
        code=code,
        message=message,
        question_id=question_id,
        context=ctx or {},
    )


# ── Blocking checks ────────────────────────────────────────────────────────────


def _check_title(aset, questions: list) -> list[ValidationFinding]:
    if not (aset.title or "").strip():
        return [_blocking("missing_title", "Assessment set must have a title before publishing.")]
    return []


def _check_category(aset, questions: list) -> list[ValidationFinding]:
    if not (aset.category or "").strip():
        return [_blocking("missing_category", "Assessment set must have a category before publishing.")]
    return []


def _check_has_active_questions(aset, questions: list) -> list[ValidationFinding]:
    if not questions:
        return [_blocking("no_active_questions", "Cannot publish: set has no active questions.")]
    return []


def _check_question_prompts(aset, questions: list) -> list[ValidationFinding]:
    return [
        _blocking("empty_prompt", f"Question #{q.id} has an empty prompt.", question_id=q.id)
        for q in questions
        if not (getattr(q, "prompt", "") or "").strip()
    ]


def _check_question_types(aset, questions: list) -> list[ValidationFinding]:
    from assessments.models import AssessmentQuestion
    valid_types = {t for t, _ in AssessmentQuestion.TYPE_CHOICES}
    return [
        _blocking(
            "invalid_question_type",
            f"Question #{q.id} has unsupported type: {q.question_type!r}.",
            question_id=q.id,
            valid_types=sorted(valid_types),
        )
        for q in questions
        if q.question_type not in valid_types
    ]


def _check_multiple_choice_structure(aset, questions: list) -> list[ValidationFinding]:
    from assessments.models import AssessmentQuestion
    findings: list[ValidationFinding] = []
    for q in questions:
        if q.question_type != AssessmentQuestion.TYPE_MULTIPLE_CHOICE:
            continue
        choices = q.choices or []
        if not isinstance(choices, list) or len(choices) < 2:
            findings.append(_blocking(
                "insufficient_choices",
                f"Multiple-choice question #{q.id} must have ≥ 2 choices (has {len(choices)}).",
                question_id=q.id,
                choice_count=len(choices),
            ))
            continue
        seen_ids: set[str] = set()
        for i, c in enumerate(choices):
            if not isinstance(c, dict):
                findings.append(_blocking(
                    "malformed_choice",
                    f"Question #{q.id} choice[{i}] is not a dict.",
                    question_id=q.id,
                ))
                continue
            cid = str(c.get("id") or c.get("value") or "")
            if not cid:
                findings.append(_blocking(
                    "missing_choice_id",
                    f"Question #{q.id} choice[{i}] missing 'id' field.",
                    question_id=q.id,
                ))
            elif cid in seen_ids:
                findings.append(_blocking(
                    "duplicate_choice_id",
                    f"Question #{q.id} has duplicate choice id: {cid!r}.",
                    question_id=q.id,
                    duplicate_id=cid,
                ))
            else:
                seen_ids.add(cid)
    return findings


def _check_correct_answers(aset, questions: list) -> list[ValidationFinding]:
    from assessments.models import AssessmentQuestion
    findings: list[ValidationFinding] = []
    for q in questions:
        # Short-text questions may have no canonical answer (rubric-graded)
        if q.correct_answer is None:
            if q.question_type != AssessmentQuestion.TYPE_SHORT_TEXT:
                findings.append(_blocking(
                    "missing_correct_answer",
                    f"Question #{q.id} (type={q.question_type}) has no correct_answer. "
                    "Cannot auto-grade without a correct answer.",
                    question_id=q.id,
                ))
            continue

        # Multiple choice: correct_answer must reference a valid choice id.
        if q.question_type == AssessmentQuestion.TYPE_MULTIPLE_CHOICE:
            choices = q.choices or []
            choice_ids = {str(c.get("id") or c.get("value") or "") for c in choices if isinstance(c, dict)}
            answers = q.correct_answer if isinstance(q.correct_answer, list) else [q.correct_answer]
            for ans in answers:
                if str(ans) not in choice_ids:
                    findings.append(_blocking(
                        "invalid_correct_answer",
                        f"Question #{q.id} correct_answer {ans!r} does not match any choice id. "
                        f"Valid ids: {sorted(choice_ids)!r}.",
                        question_id=q.id,
                        answer=str(ans),
                        valid_choice_ids=sorted(choice_ids),
                    ))
    return findings


def _check_duplicate_order(aset, questions: list) -> list[ValidationFinding]:
    from collections import Counter
    order_counts = Counter(getattr(q, "order", 0) for q in questions)
    dupes = sorted(order for order, n in order_counts.items() if n > 1)
    if dupes:
        return [_blocking(
            "duplicate_question_order",
            f"Duplicate question order values: {dupes!r}. Each question must have a unique order.",
            duplicate_orders=dupes,
        )]
    return []


def _check_points(aset, questions: list) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for q in questions:
        p = getattr(q, "points", None)
        try:
            pv = int(p)
        except (TypeError, ValueError):
            pv = -1
        if pv < 1:
            findings.append(_blocking(
                "invalid_points",
                f"Question #{q.id} has invalid points: {p!r}. Must be ≥ 1.",
                question_id=q.id,
                points=p,
            ))
    return findings


def _check_snapshot_structure(aset, questions: list) -> list[ValidationFinding]:
    """
    Pre-flight: verify the snapshot builder will produce a valid structure.
    Calls validate_snapshot_structure on a dry-run snapshot.
    """
    from .snapshot_builder import build_snapshot
    from .snapshot_compat import validate_snapshot_structure

    try:
        snap = build_snapshot(aset)
        errors = validate_snapshot_structure(snap)
        return [
            _blocking("snapshot_structure_error", f"Snapshot validation error: {e}")
            for e in errors
        ]
    except Exception as exc:
        return [_blocking("snapshot_build_error", f"Snapshot build failed: {exc}")]


# ── Warning checks ─────────────────────────────────────────────────────────────


def _warn_no_description(aset, questions: list) -> list[ValidationFinding]:
    if not (aset.description or "").strip():
        return [_warning(
            "no_description",
            "Set has no description. Students will not understand the purpose of this assessment.",
        )]
    return []


def _warn_low_question_count(aset, questions: list) -> list[ValidationFinding]:
    MIN_RECOMMENDED = 5
    if 0 < len(questions) < MIN_RECOMMENDED:
        return [_warning(
            "low_question_count",
            f"Set has only {len(questions)} question(s). "
            f"A minimum of {MIN_RECOMMENDED} is recommended for meaningful assessment.",
            count=len(questions),
            recommended_minimum=MIN_RECOMMENDED,
        )]
    return []


def _warn_large_question_count(aset, questions: list) -> list[ValidationFinding]:
    MAX_RECOMMENDED = 100
    if len(questions) > MAX_RECOMMENDED:
        return [_warning(
            "large_question_count",
            f"Set has {len(questions)} questions (max recommended: {MAX_RECOMMENDED}). "
            "Very large sets may impact student performance.",
            count=len(questions),
            recommended_maximum=MAX_RECOMMENDED,
        )]
    return []


def _warn_short_text_no_rubric(aset, questions: list) -> list[ValidationFinding]:
    from assessments.models import AssessmentQuestion
    findings: list[ValidationFinding] = []
    for q in questions:
        if q.question_type == AssessmentQuestion.TYPE_SHORT_TEXT:
            config = q.grading_config or {}
            if not config.get("accepted_answers") and not config.get("rubric"):
                findings.append(_warning(
                    "short_text_no_rubric",
                    f"Short-text question #{q.id} has no accepted_answers or rubric in "
                    "grading_config — auto-grading will not work for this question.",
                    question_id=q.id,
                ))
    return findings


def _warn_numeric_no_tolerance(aset, questions: list) -> list[ValidationFinding]:
    from assessments.models import AssessmentQuestion
    findings: list[ValidationFinding] = []
    for q in questions:
        if q.question_type == AssessmentQuestion.TYPE_NUMERIC:
            config = q.grading_config or {}
            if "tolerance" not in config and "exact" not in config:
                findings.append(_warning(
                    "numeric_no_tolerance",
                    f"Numeric question #{q.id} has no 'tolerance' in grading_config. "
                    "Only exact matches will be accepted.",
                    question_id=q.id,
                ))
    return findings


# ── Pipeline registry ──────────────────────────────────────────────────────────

# BLOCKING: all must pass for publish to proceed.
_BLOCKING_CHECKS: list = [
    _check_title,
    _check_category,
    _check_has_active_questions,
    _check_question_prompts,
    _check_question_types,
    _check_multiple_choice_structure,
    _check_correct_answers,
    _check_duplicate_order,
    _check_points,
    _check_snapshot_structure,
]

# WARNING: informational only — do not block publish.
_WARNING_CHECKS: list = [
    _warn_no_description,
    _warn_low_question_count,
    _warn_large_question_count,
    _warn_short_text_no_rubric,
    _warn_numeric_no_tolerance,
]


def validate_for_publish(
    aset: "AssessmentSet",
    questions: "list[AssessmentQuestion]",
) -> PublishValidationReport:
    """
    Run the full publish validation pipeline against aset and its active questions.

    Args:
        aset:       The AssessmentSet to validate (must already be locked via
                    select_for_update in the caller's transaction).
        questions:  Active AssessmentQuestion instances for this set (caller's
                    responsibility to pre-load them for consistency).

    Returns:
        PublishValidationReport. Check .is_publishable before proceeding.
        All BLOCKING findings MUST block publish. WARNING findings are
        informational only.
    """
    findings: list[ValidationFinding] = []

    for check_fn in _BLOCKING_CHECKS:
        findings.extend(check_fn(aset, questions))

    # Only run warning checks if the set is otherwise publishable — avoid
    # noisy warnings on a structurally broken set.
    if not any(f.severity == ValidationSeverity.BLOCKING for f in findings):
        for check_fn in _WARNING_CHECKS:
            findings.extend(check_fn(aset, questions))

    return PublishValidationReport(findings=findings)
