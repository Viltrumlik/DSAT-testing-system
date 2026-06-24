"""
SAT Simulation Rule Engine — single authoritative source of truth.

This module defines ALL official Digital SAT structural constraints used by:
  - Backend publish validation (publish_service.py)
  - Backend question serializer validation
  - Frontend mirrors (frontend/src/lib/satRules.ts — keep in sync)

NEVER scatter SAT-specific constants across models, views, or serializers.
Import from here.

Official SAT structure (Digital SAT, 2024+):
  Reading & Writing: 2 modules × 27 questions × 32 minutes each
  Math:              2 modules × 22 questions × 35 minutes each

See: https://satsuite.collegeboard.org/digital/whats-on-the-test/structure
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MockExam, Module, PracticeTest

# ── Official SAT subjects ────────────────────────────────────────────────────

SAT_SUBJECTS = ("READING_WRITING", "MATH")

# ── Per-module question counts (official Digital SAT) ───────────────────────

SAT_MODULE_QUESTION_COUNT: dict[str, int] = {
    "READING_WRITING": 27,
    "MATH": 22,
}

# ── Per-module time limits in minutes (official Digital SAT) ────────────────

SAT_MODULE_TIME_LIMIT_MINUTES: dict[str, int] = {
    "READING_WRITING": 32,
    "MATH": 35,
}

# ── Section order (deprecated — students can now start any section) ─────────
# Kept for reference only; enforcement removed from views.py.

SAT_SECTION_ORDER: list[str] = ["READING_WRITING", "MATH"]

# ── Break between sections (deprecated — break enforcement removed) ─────────
# Was: 600 seconds (10 minutes). No longer enforced.

SAT_BREAK_SECONDS: int = 0

# ── Allowed question_type values per section subject ────────────────────────
#
# Reading & Writing questions must carry type READING or WRITING.
# Math questions must carry type MATH.
# Mixing subjects in a module is an authoring error.

ALLOWED_QUESTION_TYPES_PER_SUBJECT: dict[str, frozenset[str]] = {
    "READING_WRITING": frozenset({"READING", "WRITING"}),
    "MATH": frozenset({"MATH"}),
}

# ── Module count per section (always exactly 2 for full SAT) ────────────────

SAT_MODULES_PER_SECTION = 2

# ── Full mock section requirements ─────────────────────────────────────────
#
# A full MOCK_SAT must contain BOTH subjects to faithfully simulate
# the official SAT experience (R&W section + Math section).

SAT_FULL_MOCK_REQUIRED_SUBJECTS = frozenset({"READING_WRITING", "MATH"})

# ── Score architecture (SAT 200–800 per section) ────────────────────────────
#
# Official Digital SAT scoring:
#
#   Reading & Writing section:
#     Base score:    200
#     Module 1 cap:  330  (a perfect M1 gives 200+330 = 530)
#     Module 2 cap:  270  (both perfect gives 200+330+270 = 800)
#
#   Math section:
#     Base score:    200
#     Module 1 cap:  380  (a perfect M1 gives 200+380 = 580)
#     Module 2 cap:  220  (both perfect gives 200+380+220 = 800)
#
# SCORING IS PROPORTIONAL:
#   contribution = round(correct_pts / total_pts × module_cap)
# This guarantees a perfect module always reaches its cap regardless of
# whether individual question scores are 10, 20, or 40 points.

SAT_SECTION_BASE_SCORE = 200
SAT_SECTION_MAX_SCORE = 800

# subject → {module_order → max contribution above base}
SAT_MODULE_SCORE_CAP: dict[str, dict[int, int]] = {
    "READING_WRITING": {1: 330, 2: 270},
    "MATH": {1: 380, 2: 220},
}

# subject → maximum section score when only that module is complete
SAT_MODULE_MAX_SECTION_SCORE: dict[str, dict[int, int]] = {
    # M1 perfect alone: 200 + M1_cap (M2 = 0)
    "READING_WRITING": {1: 530, 2: 800},
    "MATH":            {1: 580, 2: 800},
}

# ── Violation dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SatViolation:
    """
    A single structural violation of the SAT simulation rules.

    ``code``    — machine-readable identifier (used in tests / metrics).
    ``message`` — human-readable admin-facing description.
    ``blocking``— True when this prevents publish; False for warnings only.
    """

    code: str
    message: str
    blocking: bool = True


# ── Module-level validators ──────────────────────────────────────────────────


def validate_module(module: "Module", subject: str) -> list[SatViolation]:
    """
    Return all SAT violations for a single module row.

    ``subject`` is the parent PracticeTest.subject (READING_WRITING | MATH).
    """
    violations: list[SatViolation] = []

    questions = list(module.questions.all())
    q_count = len(questions)
    required_count = SAT_MODULE_QUESTION_COUNT.get(subject)

    if required_count is not None and q_count != required_count:
        subj_label = "Reading & Writing" if subject == "READING_WRITING" else "Math"
        violations.append(
            SatViolation(
                code="MODULE_QUESTION_COUNT",
                message=(
                    f"{subj_label} Module {module.module_order} requires exactly "
                    f"{required_count} questions (currently {q_count})."
                ),
                blocking=True,
            )
        )

    allowed_types = ALLOWED_QUESTION_TYPES_PER_SUBJECT.get(subject)
    if allowed_types:
        bad_type_qs = [q for q in questions if q.question_type not in allowed_types]
        if bad_type_qs:
            bad_types = sorted({q.question_type for q in bad_type_qs})
            allowed_display = "/".join(sorted(allowed_types))
            subj_label = "Reading & Writing" if subject == "READING_WRITING" else "Math"
            violations.append(
                SatViolation(
                    code="MODULE_QUESTION_TYPE",
                    message=(
                        f"{subj_label} Module {module.module_order} contains "
                        f"{len(bad_type_qs)} question(s) with invalid type "
                        f"({', '.join(bad_types)}). "
                        f"Only {allowed_display} allowed."
                    ),
                    blocking=True,
                )
            )

    return violations


# ── Section-level validators ─────────────────────────────────────────────────


def validate_practice_test(pt: "PracticeTest") -> list[SatViolation]:
    """
    Return all SAT violations for a PracticeTest (one section: R&W or Math).
    """
    violations: list[SatViolation] = []
    subject = getattr(pt, "subject", None)

    if subject not in SAT_SUBJECTS:
        violations.append(
            SatViolation(
                code="SECTION_INVALID_SUBJECT",
                message=f"Section subject '{subject}' is not a valid SAT subject.",
                blocking=True,
            )
        )
        return violations

    modules = list(pt.modules.all().order_by("module_order"))

    if len(modules) != SAT_MODULES_PER_SECTION:
        subj_label = "Reading & Writing" if subject == "READING_WRITING" else "Math"
        violations.append(
            SatViolation(
                code="SECTION_MODULE_COUNT",
                message=(
                    f"{subj_label} section must have exactly {SAT_MODULES_PER_SECTION} modules "
                    f"(currently {len(modules)})."
                ),
                blocking=True,
            )
        )
    else:
        for m in modules:
            violations.extend(validate_module(m, subject))

    return violations


# ── Mock-exam-level validators ───────────────────────────────────────────────


def validate_mock_exam(exam: "MockExam") -> list[SatViolation]:
    """
    Return all SAT violations for a MockExam (timed mock or midterm).

    Full MOCK_SAT: strict structural validation (both sections, correct counts).
    Midterm: relaxed — only validates that modules have questions; no fixed count.
    """
    from .models import MockExam as MockExamModel

    violations: list[SatViolation] = []
    tests = list(exam.tests.all())

    if exam.kind == MockExamModel.KIND_MIDTERM:
        # Midterms are institution-controlled: question counts are flexible.
        if len(tests) != 1:
            violations.append(
                SatViolation(
                    code="MIDTERM_SECTION_COUNT",
                    message="Midterm must have exactly one section.",
                    blocking=True,
                )
            )
            return violations
        pt = tests[0]
        need_mods = max(1, min(2, exam.midterm_module_count or 1))
        mods = list(pt.modules.all().order_by("module_order"))
        if len(mods) < need_mods:
            violations.append(
                SatViolation(
                    code="MIDTERM_MISSING_MODULES",
                    message=f"Midterm needs {need_mods} module(s) with questions.",
                    blocking=True,
                )
            )
        else:
            for m in mods[:need_mods]:
                if not list(m.questions.all()):
                    violations.append(
                        SatViolation(
                            code="MIDTERM_EMPTY_MODULE",
                            message=f"Module {m.module_order} must have at least one question.",
                            blocking=True,
                        )
                    )
        return violations

    # MOCK_SAT — full Digital SAT simulation: strict structural validation.
    if len(tests) == 0:
        violations.append(
            SatViolation(
                code="MOCK_NO_SECTIONS",
                message="Add both a Reading & Writing section and a Math section.",
                blocking=True,
            )
        )
        return violations

    subjects_present = {t.subject for t in tests}
    for required_subj in SAT_FULL_MOCK_REQUIRED_SUBJECTS:
        if required_subj not in subjects_present:
            label = "Reading & Writing" if required_subj == "READING_WRITING" else "Math"
            violations.append(
                SatViolation(
                    code="MOCK_MISSING_SECTION",
                    message=(
                        f"Full SAT mock requires a {label} section. "
                        f"Both sections must be present for simulation integrity."
                    ),
                    blocking=True,
                )
            )

    for pt in tests:
        violations.extend(validate_practice_test(pt))

    return violations


# ── Convenience: publish-ready check ────────────────────────────────────────


def mock_exam_publish_violations(exam: "MockExam") -> list[SatViolation]:
    """All blocking violations that prevent publishing this mock exam."""
    return [v for v in validate_mock_exam(exam) if v.blocking]


def practice_test_publish_violations(section: "PracticeTest") -> list[SatViolation]:
    """All blocking violations that prevent publishing this standalone section."""
    return [v for v in validate_practice_test(section) if v.blocking]


def compute_sat_module_score(
    earned_points: int | float,
    total_possible_points: int | float,
    subject: str,
    module_order: int,
) -> int:
    """
    Proportional SAT module score contribution.

    Maps weighted question correctness to the module's official point contribution:
      - Math M1 cap   = 380 → full section floor at 200+380 = 580 when perfect
      - Math M2 cap   = 220 → full section ceiling at 800 when both perfect
      - R&W M1 cap    = 330 → floor 530 when perfect
      - R&W M2 cap    = 270 → ceiling 800 when both perfect

    Using proportional scoring means the `score` field on Question acts as a
    relative weight (harder questions can count more), while a perfect module
    always yields the full cap regardless of whether questions are worth 10, 20,
    or 40 points each.

    Returns 0 when total_possible_points == 0 (empty module).
    """
    caps = SAT_MODULE_SCORE_CAP.get(subject, {})
    cap = caps.get(module_order, 0)
    if not cap or not total_possible_points:
        return 0
    fraction = max(0.0, min(1.0, float(earned_points) / float(total_possible_points)))
    return min(int(round(fraction * cap)), cap)


def is_question_type_allowed(question_type: str, subject: str) -> bool:
    """True if question_type is valid for the given section subject."""
    allowed = ALLOWED_QUESTION_TYPES_PER_SUBJECT.get(subject)
    if allowed is None:
        return True  # Unknown subject — don't block
    return question_type in allowed


def allowed_question_types_for_subject(subject: str) -> list[str]:
    """Ordered list of allowed question_type values for the given subject."""
    allowed = ALLOWED_QUESTION_TYPES_PER_SUBJECT.get(subject)
    if allowed is None:
        return ["MATH", "READING", "WRITING"]
    # Return in a stable, human-friendly order
    order = ["MATH", "READING", "WRITING"]
    return [t for t in order if t in allowed]
