/**
 * Wire contract for the SAT exam engine (`/api/exams/attempts/...`).
 *
 * This is the single source of truth for the Testing Simulation module. Every
 * payload that crosses the network is validated here with Zod, so the rest of
 * the module can trust its types absolutely. Nothing else in
 * `features/testing-simulation` should redefine these shapes.
 */
import { z } from "zod";

/** Raised when an exam endpoint returns JSON that violates the contract. */
export class InvalidAttemptPayloadError extends Error {
  readonly issues: z.ZodIssue[];
  constructor(error: z.ZodError, context?: string) {
    super(
      `[testing-simulation] Invalid attempt payload${context ? ` (${context})` : ""}: ` +
        error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
    );
    this.name = "InvalidAttemptPayloadError";
    this.issues = error.issues;
  }
}

/** Canonical engine states (mirrors backend `attempt_state_machine.py`). */
export const ATTEMPT_STATE = {
  NOT_STARTED: "NOT_STARTED",
  MODULE_1_ACTIVE: "MODULE_1_ACTIVE",
  MODULE_1_SUBMITTED: "MODULE_1_SUBMITTED",
  MODULE_2_ACTIVE: "MODULE_2_ACTIVE",
  MODULE_2_SUBMITTED: "MODULE_2_SUBMITTED",
  SCORING: "SCORING",
  COMPLETED: "COMPLETED",
  ABANDONED: "ABANDONED",
} as const;

export const attemptStateSchema = z.nativeEnum(ATTEMPT_STATE);
export type AttemptState = z.infer<typeof attemptStateSchema>;

const moduleOrderSchema = z.number().int().min(1).max(2);

/** A single answerable question inside the active module. */
export const examQuestionSchema = z
  .object({
    id: z.number(),
    question_type: z.enum(["MATH", "READING", "WRITING"]),
    question_text: z.string(),
    question_prompt: z.string().optional(),
    question_image: z.string().nullable().optional(),
    is_math_input: z.boolean().optional(),
    /** Dynamic A/B/C/D map; values are string or `{ text, image }`. */
    options: z.unknown().optional(),
  })
  .passthrough();
export type ExamQuestion = z.infer<typeof examQuestionSchema>;

/** The module the student is currently inside, with its question list. */
export const activeModuleSchema = z.object({
  id: z.number(),
  module_order: moduleOrderSchema,
  time_limit_minutes: z.number(),
  questions: z.array(examQuestionSchema),
});
export type ActiveModule = z.infer<typeof activeModuleSchema>;

const practiceTestDetailsSchema = z
  .object({
    id: z.number(),
    subject: z.string(),
    title: z.string(),
    mock_exam_id: z.number().nullable().optional(),
    mock_kind: z.string().nullable().optional(),
    modules: z.array(
      z.object({
        id: z.number(),
        module_order: moduleOrderSchema,
        time_limit_minutes: z.number(),
      }),
    ),
  })
  .passthrough();

/**
 * Full attempt snapshot. Server-authoritative for timer (`remaining_seconds`,
 * `server_now`, `module_duration_seconds`), state, and concurrency
 * (`version_number`). The client renders this; it never invents timing.
 */
export const attemptSchema = z
  .object({
    id: z.number(),
    current_state: attemptStateSchema,
    version_number: z.number(),

    practice_test_details: practiceTestDetailsSchema,

    current_module: z.number().nullable(),
    current_module_details: activeModuleSchema.nullable(),
    current_module_start_time: z.string().nullable(),

    // Server-authoritative timing.
    server_now: z.string(),
    remaining_seconds: z.number().nullable(),
    module_duration_seconds: z.number().nullable(),

    // Persisted per-module work (rehydration after refresh).
    current_module_saved_answers: z.record(z.string(), z.unknown()).nullable(),
    current_module_flagged_questions: z.array(z.number()).nullable(),

    // Lifecycle flags.
    is_completed: z.boolean(),
    is_expired: z.boolean(),
    is_paused: z.boolean().default(false),
    can_submit: z.boolean().optional(),
    can_resume: z.boolean().optional(),
    results_ready: z.boolean().optional(),

    score: z.number().nullable().optional(),
    completed_modules: z.array(z.number()).optional(),
  })
  .passthrough();
export type Attempt = z.infer<typeof attemptSchema>;

export function parseAttempt(data: unknown, context?: string): Attempt {
  const result = attemptSchema.safeParse(data);
  if (!result.success) {
    if (process.env.NODE_ENV !== "production") {
      console.error("[testing-simulation] attempt validation failed", context, result.error.flatten(), data);
    }
    throw new InvalidAttemptPayloadError(result.error, context);
  }
  return result.data;
}

/** Coerce the server's saved-answer map into the string form controlled inputs use. */
export function normalizeSavedAnswers(raw: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (v == null) continue;
    out[k] = typeof v === "string" ? v : String(v);
  }
  return out;
}

export function normalizeFlagged(raw: number[] | null | undefined): number[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((n): n is number => typeof n === "number" && Number.isFinite(n));
}
