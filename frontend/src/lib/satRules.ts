/**
 * SAT Simulation Rule Engine — canonical frontend source of truth.
 *
 * This module mirrors backend/exams/sat_rules.py.
 * When changing SAT structural rules, update BOTH files.
 *
 * Official Digital SAT structure (2024+):
 *   Reading & Writing: 2 modules × 27 questions × 32 minutes each
 *   Math:              2 modules × 22 questions × 35 minutes each
 */

// ── Official SAT subjects ────────────────────────────────────────────────────

export type SatSubject = "READING_WRITING" | "MATH";

export const SAT_SUBJECTS: readonly SatSubject[] = ["READING_WRITING", "MATH"];

export function isSatSubject(s: string): s is SatSubject {
  return s === "READING_WRITING" || s === "MATH";
}

// ── Question types ──────────────────────────────────────────────────────────

export type SatQuestionType = "MATH" | "READING" | "WRITING";

export const ALL_QUESTION_TYPES: readonly SatQuestionType[] = ["MATH", "READING", "WRITING"];

// ── Per-module question counts ───────────────────────────────────────────────

export const SAT_MODULE_QUESTION_COUNT: Record<SatSubject, number> = {
  READING_WRITING: 27,
  MATH: 22,
} as const;

// ── Per-module time limits (minutes) ────────────────────────────────────────

export const SAT_MODULE_TIME_LIMIT_MINUTES: Record<SatSubject, number> = {
  READING_WRITING: 32,
  MATH: 35,
} as const;

// ── Allowed question types per section subject ───────────────────────────────

export const ALLOWED_QUESTION_TYPES: Record<SatSubject, readonly SatQuestionType[]> = {
  READING_WRITING: ["READING", "WRITING"],
  MATH: ["MATH"],
} as const;

// ── Modules per section ──────────────────────────────────────────────────────

export const SAT_MODULES_PER_SECTION = 2;

// ── Score architecture ───────────────────────────────────────────────────────
//
// Official Digital SAT scoring (must match backend sat_rules.py exactly):
//
//   Reading & Writing:
//     Base: 200  |  M1 cap: 330 (floor 530)  |  M2 cap: 270 (ceiling 800)
//   Math:
//     Base: 200  |  M1 cap: 380 (floor 580)  |  M2 cap: 220 (ceiling 800)
//
// Scoring is PROPORTIONAL:
//   contribution = round(correct_pts / total_pts × module_cap)
// A perfect module always yields the full cap regardless of question score weights.

export const SAT_SECTION_BASE_SCORE = 200;
export const SAT_SECTION_MAX_SCORE = 800;

/** Maximum contribution per module above the 200 base. */
export const SAT_MODULE_SCORE_CAP: Record<SatSubject, Record<1 | 2, number>> = {
  READING_WRITING: { 1: 330, 2: 270 },
  MATH:            { 1: 380, 2: 220 },
} as const;

/**
 * Maximum section score when only through Module N with perfection.
 * E.g. Math M1 perfect alone = 580; both perfect = 800.
 */
export const SAT_MODULE_MAX_SECTION_SCORE: Record<SatSubject, Record<1 | 2, number>> = {
  READING_WRITING: { 1: 530, 2: 800 },
  MATH:            { 1: 580, 2: 800 },
} as const;

/**
 * Compute proportional SAT module score contribution.
 * Mirrors backend sat_rules.compute_sat_module_score().
 *
 * ``earnedPoints``   — weighted sum of scores for correct questions
 * ``totalPoints``    — weighted sum of scores for all questions
 * ``subject``        — READING_WRITING | MATH
 * ``moduleOrder``    — 1 or 2
 */
export function computeSatModuleScore(
  earnedPoints: number,
  totalPoints: number,
  subject: string | undefined | null,
  moduleOrder: 1 | 2,
): number {
  if (!subject || !isSatSubject(subject) || !totalPoints) return 0;
  const cap = SAT_MODULE_SCORE_CAP[subject][moduleOrder];
  if (!cap) return 0;
  const fraction = Math.max(0, Math.min(1, earnedPoints / totalPoints));
  return Math.min(Math.round(fraction * cap), cap);
}

/**
 * Compute the full SAT section score (200–800) from per-module earned points.
 * Mirrors the logic in TestAttempt.complete_test().
 *
 * ``modules`` — array of {earnedPoints, totalPoints, moduleOrder}
 */
export function computeSatSectionScore(
  subject: string | undefined | null,
  modules: Array<{ earnedPoints: number; totalPoints: number; moduleOrder: 1 | 2 }>,
): number {
  let total = SAT_SECTION_BASE_SCORE;
  for (const m of modules) {
    total += computeSatModuleScore(m.earnedPoints, m.totalPoints, subject, m.moduleOrder);
  }
  return Math.min(total, SAT_SECTION_MAX_SCORE);
}

// ── Subject display labels ───────────────────────────────────────────────────

export const SAT_SUBJECT_LABEL: Record<SatSubject, string> = {
  READING_WRITING: "Reading & Writing",
  MATH: "Mathematics",
} as const;

export const SAT_QUESTION_TYPE_LABEL: Record<SatQuestionType, string> = {
  MATH: "Math",
  READING: "Reading",
  WRITING: "Writing",
} as const;

// ── Helper utilities ─────────────────────────────────────────────────────────

/**
 * Returns the allowed question types for a given section subject.
 * Falls back to all types for unknown subjects.
 */
export function allowedQuestionTypesForSubject(
  subject: string | undefined | null,
): readonly SatQuestionType[] {
  if (!subject || !isSatSubject(subject)) return ALL_QUESTION_TYPES;
  return ALLOWED_QUESTION_TYPES[subject];
}

/**
 * Returns true if the question_type is valid for the given section subject.
 */
export function isQuestionTypeAllowed(
  questionType: string,
  subject: string | undefined | null,
): boolean {
  if (!subject || !isSatSubject(subject)) return true;
  return (ALLOWED_QUESTION_TYPES[subject] as readonly string[]).includes(questionType);
}

/**
 * Returns the required question count for a given subject.
 * Returns null for unknown subjects (no constraint enforced).
 */
export function requiredQuestionCount(subject: string | undefined | null): number | null {
  if (!subject || !isSatSubject(subject)) return null;
  return SAT_MODULE_QUESTION_COUNT[subject];
}

/**
 * Returns the required time limit (minutes) for a given subject.
 */
export function requiredTimeLimitMinutes(subject: string | undefined | null): number | null {
  if (!subject || !isSatSubject(subject)) return null;
  return SAT_MODULE_TIME_LIMIT_MINUTES[subject];
}

// ── Module composition violation types ──────────────────────────────────────

export type ModuleViolation = {
  code: string;
  message: string;
};

/**
 * Validate the composition of questions in a module against SAT rules.
 * Returns an array of violations (empty = valid).
 *
 * ``questions`` — minimal question shape: {question_type: string}
 * ``subject``   — the PracticeTest.subject for this module
 * ``moduleOrder`` — 1 or 2 (for human-readable messages)
 */
export function validateModuleComposition(
  questions: Array<{ question_type: string }>,
  subject: string | undefined | null,
  moduleOrder: number = 1,
): ModuleViolation[] {
  if (!subject || !isSatSubject(subject)) return [];

  const violations: ModuleViolation[] = [];
  const required = SAT_MODULE_QUESTION_COUNT[subject];
  const subjectLabel = SAT_SUBJECT_LABEL[subject];

  if (questions.length !== required) {
    violations.push({
      code: "MODULE_QUESTION_COUNT",
      message:
        `${subjectLabel} Module ${moduleOrder} requires exactly ${required} questions ` +
        `(currently ${questions.length}).`,
    });
  }

  const allowed = ALLOWED_QUESTION_TYPES[subject] as readonly string[];
  const wrongType = questions.filter((q) => !allowed.includes(q.question_type));
  if (wrongType.length > 0) {
    const badTypes = [...new Set(wrongType.map((q) => q.question_type))].join(", ");
    const allowedDisplay = allowed.join("/");
    violations.push({
      code: "MODULE_QUESTION_TYPE",
      message:
        `${subjectLabel} Module ${moduleOrder} contains ${wrongType.length} question(s) ` +
        `with invalid type (${badTypes}). Only ${allowedDisplay} allowed.`,
    });
  }

  return violations;
}

// ── Progress helpers for authoring UI ───────────────────────────────────────

export type ModuleProgress = {
  /** Current question count */
  current: number;
  /** Required question count for this subject (null = no constraint) */
  required: number | null;
  /** Fraction 0–1 toward requirement (null if no constraint) */
  fraction: number | null;
  /** True when current === required */
  complete: boolean;
  /** True when current > required */
  over: boolean;
  /** Display string e.g. "19 / 22" */
  label: string;
};

export function getModuleProgress(
  currentCount: number,
  subject: string | undefined | null,
): ModuleProgress {
  const required = requiredQuestionCount(subject);

  if (required === null) {
    return {
      current: currentCount,
      required: null,
      fraction: null,
      complete: false,
      over: false,
      label: String(currentCount),
    };
  }

  const complete = currentCount === required;
  const over = currentCount > required;
  const fraction = Math.min(currentCount / required, 1);

  return {
    current: currentCount,
    required,
    fraction,
    complete,
    over,
    label: `${currentCount} / ${required}`,
  };
}

// ── Type mismatch warnings ───────────────────────────────────────────────────

/**
 * Returns a warning message if the question_type is wrong for the subject,
 * or null if valid.
 */
export function questionTypeWarning(
  questionType: string,
  subject: string | undefined | null,
): string | null {
  if (!subject || !isSatSubject(subject)) return null;
  if (isQuestionTypeAllowed(questionType, subject)) return null;

  const allowed = allowedQuestionTypesForSubject(subject)
    .map((t) => SAT_QUESTION_TYPE_LABEL[t])
    .join(" or ");
  const subjectLabel = SAT_SUBJECT_LABEL[subject];
  const typeName = SAT_QUESTION_TYPE_LABEL[questionType as SatQuestionType] ?? questionType;

  return (
    `${typeName} questions are not allowed in a ${subjectLabel} module. ` +
    `Use ${allowed} question types here.`
  );
}
