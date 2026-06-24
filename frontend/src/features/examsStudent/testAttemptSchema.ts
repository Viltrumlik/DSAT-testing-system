import { z } from "zod";

/** Thrown when GET/POST exam endpoints return JSON that does not match the contract. */
export class InvalidTestAttemptPayloadError extends Error {
  readonly zodError: z.ZodError;

  constructor(zodError: z.ZodError, context?: string) {
    super(
      `[exam] Invalid TestAttempt${context ? ` (${context})` : ""}: ${zodError.issues.map((i) => i.path.join(".").concat(": ", i.message)).join("; ")}`,
    );
    this.name = "InvalidTestAttemptPayloadError";
    this.zodError = zodError;
  }
}

const moduleOrderSchema = z.union([z.literal(1), z.literal(2), z.number().int().min(1).max(2)]);

/** Runner question row (serializer adds dynamic `options` map). */
export const examQuestionSchema = z
  .object({
    id: z.number(),
    question_type: z.enum(["MATH", "READING", "WRITING"]),
    question_text: z.string(),
    question_prompt: z.string().optional(),
    question_image: z.string().nullable().optional(),
    is_math_input: z.boolean().optional(),
    option_a_image: z.string().nullable().optional(),
    option_b_image: z.string().nullable().optional(),
    option_c_image: z.string().nullable().optional(),
    option_d_image: z.string().nullable().optional(),
  })
  .passthrough();

export type ExamQuestion = z.infer<typeof examQuestionSchema>;

export const examAttemptModuleDetailSchema = z.object({
  id: z.number(),
  module_order: moduleOrderSchema,
  time_limit_minutes: z.number(),
  questions: z.array(examQuestionSchema),
});

export type ExamAttemptModuleDetail = z.infer<typeof examAttemptModuleDetailSchema>;

const pastpaperPackBriefSchema = z
  .object({
    id: z.number(),
    title: z.string().optional(),
    practice_date: z.string().nullable().optional(),
    label: z.string().optional(),
    form_type: z.enum(["INTERNATIONAL", "US"]).optional(),
  })
  .passthrough();

export const attemptPracticeTestDetailsSchema = z.object({
  id: z.number(),
  subject: z.string(),
  title: z.string(),
  label: z.string().nullable().optional(),
  form_type: z.string().nullable().optional(),
  practice_date: z.string().nullable().optional(),
  pastpaper_pack: pastpaperPackBriefSchema.nullable().optional(),
  is_active: z.boolean().optional(),
  mock_exam_id: z.number().nullable().optional(),
  mock_kind: z.string().nullable().optional(),
  modules: z.array(
    z.object({
      id: z.number(),
      module_order: moduleOrderSchema,
      time_limit_minutes: z.number(),
    }),
  ),
});

export const attemptModuleQuestionResultSchema = z.object({
  id: z.number(),
  is_correct: z.boolean(),
  student_answer: z.unknown().nullable(),
  correct_answers: z.string(),
  score: z.number(),
  text: z.string(),
  question_prompt: z.string().optional(),
  image: z.string().nullable().optional(),
  type: z.string(),
  options: z.unknown().nullable(),
  is_math_input: z.boolean(),
});

export const attemptModuleResultsItemSchema = z.object({
  module_id: z.number(),
  module_order: z.number(),
  module_earned: z.number(),
  capped_earned: z.number(),
  questions: z.array(attemptModuleQuestionResultSchema),
});

const currentStateSchema = z.enum([
  "NOT_STARTED",
  "MODULE_1_ACTIVE",
  "MODULE_1_SUBMITTED",
  "MODULE_2_ACTIVE",
  "MODULE_2_SUBMITTED",
  "SCORING",
  "COMPLETED",
  "ABANDONED",
]);

const enginePhaseSchema = z.enum(["pending", "active", "scoring", "completed", "abandoned", "other"]);

/** Minimum safe shape for `student_details`; extra fields allowed (User varies by role). */
const studentDetailsSchema = z
  .object({
    id: z.number(),
    first_name: z.string().optional(),
    last_name: z.string().optional(),
  })
  .passthrough();

/**
 * Full TestAttempt as returned by `/api/exams/attempts/...` (status, submit, start, resume).
 * Aligns with generated OpenAPI `components["schemas"]["TestAttempt"]`.
 */
export const testAttemptSchema = z.object({
  id: z.number(),
  practice_test: z.number(),
  practice_test_details: attemptPracticeTestDetailsSchema,
  student: z.number(),
  student_details: studentDetailsSchema,
  started_at: z.string().nullable(),
  submitted_at: z.string().nullable(),
  current_module: z.number().nullable(),
  current_module_details: examAttemptModuleDetailSchema.nullable(),
  current_module_start_time: z.string().nullable(),
  current_state: currentStateSchema,
  module_1_started_at: z.string().nullable(),
  module_1_submitted_at: z.string().nullable(),
  module_2_started_at: z.string().nullable(),
  module_2_submitted_at: z.string().nullable(),
  scoring_started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  version_number: z.number(),
  is_completed: z.boolean(),
  is_expired: z.boolean(),
  score: z.number().nullable(),
  completed_modules: z.array(z.number()),
  module_results: z.array(attemptModuleResultsItemSchema).nullable(),
  server_now: z.string(),
  current_module_saved_answers: z.record(z.string(), z.unknown()).nullable(),
  current_module_flagged_questions: z.array(z.number()).nullable(),
  remaining_seconds: z.number().nullable(),
  module_duration_seconds: z.number().nullable(),
  module_started_at: z.string().nullable(),
  active_module_order: z.number().nullable(),
  can_submit: z.boolean(),
  can_resume: z.boolean(),
  results_ready: z.boolean(),
  engine_phase: enginePhaseSchema,
  scoring_notice: z.string().nullable(),
  is_paused: z.boolean().default(false),
});

export type TestAttempt = z.infer<typeof testAttemptSchema>;

export function parseTestAttempt(data: unknown, context?: string): TestAttempt {
  const r = testAttemptSchema.safeParse(data);
  if (!r.success) {
    console.error("[exam] TestAttempt validation failed", context ?? "", r.error.flatten(), data);
    throw new InvalidTestAttemptPayloadError(r.error, context);
  }
  return r.data;
}

/** Local draft written by the runner (not the API). */
export const examLocalDraftSchema = z.object({
  answers: z.record(z.string(), z.string()),
  flagged: z.array(z.number()),
  v: z.number().nullable(),
  moduleId: z.number(),
});

export type ExamLocalDraft = z.infer<typeof examLocalDraftSchema>;

export function parseExamLocalDraft(raw: unknown): ExamLocalDraft | null {
  const r = examLocalDraftSchema.safeParse(raw);
  if (!r.success) {
    console.warn("[exam] Invalid local exam draft; discarding", r.error.flatten(), raw);
    return null;
  }
  return r.data;
}

/**
 * Coerce server saved-answer map to string values for controlled inputs.
 * Logs when the payload is null/undefined or not an object.
 */
export function normalizeSavedAnswersForForm(
  raw: Record<string, unknown> | null | undefined,
  logLabel: string,
): Record<string, string> {
  if (raw == null) {
    console.warn(`[exam] ${logLabel}: current_module_saved_answers is null/undefined; using empty map`);
    return {};
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    console.warn(`[exam] ${logLabel}: current_module_saved_answers is not an object; using empty map`, raw);
    return {};
  }
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (v == null) continue;
    out[k] = typeof v === "string" ? v : String(v);
  }
  return out;
}

export function normalizeFlaggedList(
  raw: number[] | null | undefined,
  logLabel: string,
): number[] {
  if (raw == null) {
    console.warn(`[exam] ${logLabel}: current_module_flagged_questions is null/undefined; using []`);
    return [];
  }
  if (!Array.isArray(raw)) {
    console.warn(`[exam] ${logLabel}: current_module_flagged_questions is not an array; using []`, raw);
    return [];
  }
  return raw.filter((n): n is number => typeof n === "number" && Number.isFinite(n));
}

/** Bootstrap / 404 recovery: only fields we read from raw session JSON. */
export const attemptBootstrapHintsSchema = z
  .object({
    id: z.number().optional(),
    practice_test: z.number().optional(),
    practice_test_id: z.number().optional(),
    practice_test_details: z
      .object({
        id: z.number().optional(),
        pk: z.number().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

export function parseAttemptBootstrapHints(raw: unknown): { practiceTestId: number } | null {
  const r = attemptBootstrapHintsSchema.safeParse(raw);
  if (!r.success) {
    console.warn("[exam] Invalid bootstrap hints for routing", r.error.flatten());
    return null;
  }
  const o = r.data;
  const ptId =
    o.practice_test_details?.id ??
    o.practice_test_details?.pk ??
    o.practice_test ??
    o.practice_test_id;
  if (ptId == null || !Number.isFinite(ptId)) return null;
  return { practiceTestId: Number(ptId) };
}
