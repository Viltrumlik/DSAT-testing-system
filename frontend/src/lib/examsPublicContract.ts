import { z } from "zod";
import type { components } from "@/lib/openapi-types";
import { parseTestAttempt, type TestAttempt } from "@/features/examsStudent/testAttemptSchema";

/** Aligns with OpenAPI `components["schemas"]["PracticeTest"]` (student portal). */
export type PracticeTestPublic = components["schemas"]["PracticeTest"];
/** Aligns with OpenAPI `components["schemas"]["MockExam"]`. */
export type MockExamPublic = components["schemas"]["MockExam"];

/** Normalized envelope: bare JSON arrays and DRF `{ results }` payloads both map here. */
export type NormalizedExamList<T> = {
  items: T[];
  count: number | null;
  next: string | null;
  previous: string | null;
};

export function emptyNormalizedExamList<T>(): NormalizedExamList<T> {
  return { items: [], count: null, next: null, previous: null };
}

export class InvalidApiPayloadError extends Error {
  readonly zodError: z.ZodError;
  readonly endpoint: string;
  readonly payload: unknown;

  constructor(endpoint: string, zodError: z.ZodError, payload: unknown) {
    const detail = zodError.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
    super(`[api] Invalid JSON for ${endpoint}: ${detail}`);
    this.name = "InvalidApiPayloadError";
    this.zodError = zodError;
    this.endpoint = endpoint;
    this.payload = payload;
  }
}

export function parseWithSchema<T>(
  schema: z.ZodType<T>,
  data: unknown,
  endpoint: string,
): T {
  const r = schema.safeParse(data);
  if (!r.success) {
    console.error("[api] Schema validation failed", endpoint, r.error.flatten(), data);
    throw new InvalidApiPayloadError(endpoint, r.error, data);
  }
  return r.data;
}

const drfResultsEnvelopeSchema = z.object({
  results: z.array(z.unknown()),
  count: z.number().optional().nullable(),
  next: z.union([z.string(), z.null()]).optional(),
  previous: z.union([z.string(), z.null()]).optional(),
});

/**
 * Accepts a bare array or DRF pagination object. Throws if neither shape matches.
 */
export function extractNormalizedListEnvelope(
  data: unknown,
  endpoint: string,
): { itemsUnknown: unknown[]; count: number | null; next: string | null; previous: string | null } {
  if (Array.isArray(data)) {
    return { itemsUnknown: data, count: data.length, next: null, previous: null };
  }
  const paged = drfResultsEnvelopeSchema.safeParse(data);
  if (paged.success) {
    const o = paged.data;
    const count = typeof o.count === "number" && Number.isFinite(o.count) ? o.count : null;
    const next = o.next === null || o.next === undefined ? null : String(o.next);
    const previous =
      o.previous === null || o.previous === undefined ? null : String(o.previous);
    return {
      itemsUnknown: o.results,
      count,
      next,
      previous,
    };
  }
  console.error("[api] List response neither array nor { results[] }", endpoint, data, paged.error.flatten());
  throw new InvalidApiPayloadError(endpoint, paged.error, data);
}

const moduleOrderSchema = z.union([z.literal(1), z.literal(2)]);

const moduleListPublicSchema = z.object({
  id: z.number(),
  module_order: moduleOrderSchema,
  time_limit_minutes: z.number(),
});

export const pastpaperPackBriefStudentSchema = z
  .object({
    id: z.number(),
    title: z.string().optional(),
    practice_date: z.string().nullable().optional(),
    label: z.string().optional(),
    form_type: z.enum(["INTERNATIONAL", "US"]).optional(),
  })
  .passthrough();

/** Student `PracticeTest` (portal / exams / list + retrieve). */
export const practiceTestPublicSchema = z
  .object({
    id: z.number(),
    title: z.string().optional(),
    practice_date: z.string().nullable().optional(),
    subject: z.string(),
    label: z.string().optional(),
    form_type: z.enum(["INTERNATIONAL", "US"]).optional(),
    modules: z.array(moduleListPublicSchema),
    created_at: z.string(),
    /**
     * Former `PastpaperPack` grouping (removed on the backend). Sections are now
     * standalone; `collection_name` carries the former pack title for labeling.
     * `pastpaper_pack` is accepted (optional/nullable) only for backward compat.
     */
    collection_name: z.string().optional(),
    is_published: z.boolean().optional(),
    pastpaper_pack: pastpaperPackBriefStudentSchema.nullable().optional(),
    mock_exam_id: z.number().nullable(),
  })
  .passthrough();

const mockExamKindSchema = z.enum(["MOCK_SAT", "MIDTERM"]);
const midtermSubjectSchema = z.enum(["READING_WRITING", "MATH"]);

/** Student `MockExam` (timed mocks list + retrieve). */
export const mockExamPublicSchema = z
  .object({
    id: z.number(),
    title: z.string(),
    practice_date: z.string().nullable().optional(),
    is_active: z.boolean().optional(),
    is_published: z.boolean().optional(),
    published_at: z.string().nullable().optional(),
    kind: mockExamKindSchema.optional(),
    midterm_subject: midtermSubjectSchema.optional(),
    midterm_module_count: z.number().optional(),
    midterm_module1_minutes: z.number().optional(),
    midterm_module2_minutes: z.number().optional(),
    tests: z.array(practiceTestPublicSchema),
  })
  .passthrough();

export function parsePracticeTestPublicPayload(data: unknown, endpoint: string): PracticeTestPublic {
  return parseWithSchema(practiceTestPublicSchema, data, endpoint) as PracticeTestPublic;
}

export function parsePracticeTestPublicList(
  data: unknown,
  endpoint: string,
): NormalizedExamList<PracticeTestPublic> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) =>
    parseWithSchema(practiceTestPublicSchema, row, `${endpoint}[${i}]`),
  ) as PracticeTestPublic[];
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}

export function parseMockExamPublicPayload(data: unknown, endpoint: string): MockExamPublic {
  return parseWithSchema(mockExamPublicSchema, data, endpoint) as MockExamPublic;
}

export function parseMockExamPublicList(
  data: unknown,
  endpoint: string,
): NormalizedExamList<MockExamPublic> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) =>
    parseWithSchema(mockExamPublicSchema, row, `${endpoint}[${i}]`),
  ) as MockExamPublic[];
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}

export function parseTestAttemptApiPayload(data: unknown, endpoint: string): TestAttempt {
  return parseTestAttempt(data, endpoint);
}

export function parseTestAttemptList(
  data: unknown,
  endpoint: string,
): NormalizedExamList<TestAttempt> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) => parseTestAttempt(row, `${endpoint}[${i}]`));
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}
