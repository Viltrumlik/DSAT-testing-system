import { z } from "zod";
import type { components } from "@/lib/openapi-types";
import {
  extractNormalizedListEnvelope,
  InvalidApiPayloadError,
  parseWithSchema,
  type NormalizedExamList,
} from "@/lib/examsPublicContract";

export type UserMe = components["schemas"]["UserMe"];
export type Classroom = components["schemas"]["Classroom"];
export type Assignment = components["schemas"]["Assignment"];
export type BulkAssignmentDispatch = components["schemas"]["BulkAssignmentDispatch"];

/** Re-use the same list envelope as exams public API (items + optional DRF pagination). */
export type NormalizedList<T> = NormalizedExamList<T>;

export function emptyNormalizedList<T>(): NormalizedList<T> {
  return { items: [], count: null, next: null, previous: null };
}

const looseObjectRecordSchema = z.record(z.string(), z.unknown());

/** Login/register/refresh bodies omit tokens; accept any JSON object (including `{}`). */
export function parseAuthSessionPayload(data: unknown, endpoint: string): Record<string, unknown> {
  if (data == null) return {};
  const r = looseObjectRecordSchema.safeParse(data);
  if (!r.success) {
    console.error("[api] Auth response must be object or null", endpoint, data);
    throw new InvalidApiPayloadError(endpoint, r.error, data);
  }
  return r.data as Record<string, unknown>;
}

const csrfTokenSchema = z.object({
  csrfToken: z.string(),
});

export function parseCsrfPayload(data: unknown, endpoint: string) {
  return parseWithSchema(csrfTokenSchema, data, endpoint);
}

const userMeLastMockSchema = z.object({
  score: z.number().nullable(),
  mock_exam_title: z.string().nullable().optional(),
  practice_test_subject: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
});

/** Mirrors `UserMe` OpenAPI schema — `.passthrough()` allows forward-compatible serializer fields. */
export const userMeResponseSchema = z
  .object({
    id: z.number(),
    email: z.string().optional(),
    username: z.union([z.string(), z.null()]).optional(),
    first_name: z.string().optional(),
    last_name: z.string().optional(),
    phone_number: z.union([z.string(), z.null()]).optional(),
    is_frozen: z.boolean(),
    is_admin: z.boolean(),
    telegram_linked: z.boolean(),
    profile_image_url: z.union([z.string(), z.null()]).optional(),
    sat_exam_date: z.union([z.string(), z.null()]).optional(),
    target_score: z.union([z.number(), z.null()]).optional(),
    target_english: z.union([z.number(), z.null()]).optional(),
    target_math: z.union([z.number(), z.null()]).optional(),
    last_mock_result: userMeLastMockSchema.nullable().optional(),
    role: z.string(),
    subject: z.union([z.literal("math"), z.literal("english"), z.null()]),
    permissions: z.array(z.string()),
    last_password_change: z.union([z.string(), z.null()]),
    security_step_up_active: z.boolean(),
    has_recent_security_alerts: z.boolean(),
  })
  .passthrough();

export function parseUserMePayload(data: unknown, endpoint: string): UserMe {
  return parseWithSchema(userMeResponseSchema, data, endpoint) as UserMe;
}

const classroomRowSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    subject: z.enum(["ENGLISH", "MATH"]),
    lesson_days: z.enum(["ODD", "EVEN"]),
    join_code: z.string(),
    created_at: z.string().optional(),
    members_count: z.number().optional(),
  })
  .passthrough();

export function parseClassroomList(data: unknown, endpoint: string): NormalizedList<Classroom> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) =>
    parseWithSchema(classroomRowSchema, row, `${endpoint}[${i}]`),
  ) as Classroom[];
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}

const assignmentRowSchema = z
  .object({
    id: z.number(),
    title: z.string(),
    practice_scope: z.enum(["BOTH", "ENGLISH", "MATH"]).optional(),
    created_at: z.string(),
    submissions_count: z.number().optional(),
  })
  .passthrough();

export function parseAssignmentList(data: unknown, endpoint: string): NormalizedList<Assignment> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) =>
    parseWithSchema(assignmentRowSchema, row, `${endpoint}[${i}]`),
  ) as Assignment[];
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}

const bulkDispatchRowSchema = z
  .object({
    id: z.number(),
    kind: z.enum(["pastpaper", "timed_mock", "mixed"]),
    status: z.enum(["pending", "processing", "delivered", "completed", "failed"]),
    created_at: z.string(),
  })
  .passthrough();

export function parseBulkAssignmentHistoryList(
  data: unknown,
  endpoint: string,
): NormalizedList<BulkAssignmentDispatch> {
  const env = extractNormalizedListEnvelope(data, endpoint);
  const items = env.itemsUnknown.map((row, i) =>
    parseWithSchema(bulkDispatchRowSchema, row, `${endpoint}[${i}]`),
  ) as BulkAssignmentDispatch[];
  return {
    items,
    count: env.count,
    next: env.next,
    previous: env.previous,
  };
}

export function parseBulkAssignResponse(data: unknown, endpoint: string): Record<string, unknown> {
  return parseAuthSessionPayload(data, endpoint);
}
