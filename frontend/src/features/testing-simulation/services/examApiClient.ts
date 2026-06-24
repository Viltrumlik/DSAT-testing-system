/**
 * Typed client for the SAT exam engine. Every method validates its response
 * through `parseAttempt`, so callers always receive a trusted `Attempt`.
 *
 * Transport is the shared, auth-aware axios instance (`@/lib/api`) — it carries
 * the JWT access token and refresh interceptors. Only the exam-specific request
 * shapes are owned here.
 */
import api from "@/lib/api";
import { type Attempt, parseAttempt } from "../types";

interface MutationOptions {
  idempotencyKey?: string;
  expectedVersionNumber?: number;
}

function idemHeaders(key?: string): Record<string, string> | undefined {
  return key ? { "Idempotency-Key": key } : undefined;
}

function withVersion(body: Record<string, unknown>, version?: number): Record<string, unknown> {
  if (version != null) body.expected_version_number = version;
  return body;
}

export const examApi = {
  /** Canonical poll endpoint; falls back to the legacy retrieve route. */
  async getStatus(attemptId: number): Promise<Attempt> {
    try {
      const r = await api.get(`/exams/attempts/${attemptId}/status/`);
      return parseAttempt(r.data, "GET status");
    } catch {
      const r = await api.get(`/exams/attempts/${attemptId}/`);
      return parseAttempt(r.data, "GET attempt");
    }
  },

  /** Transition NOT_STARTED → MODULE_1_ACTIVE. Idempotent via key. */
  async start(attemptId: number, idempotencyKey?: string): Promise<Attempt> {
    const r = await api.post(`/exams/attempts/${attemptId}/start/`, {}, { headers: idemHeaders(idempotencyKey) });
    return parseAttempt(r.data, "POST start");
  },

  /** Pause the wall clock (pastpapers only; mocks disallow pause server-side). */
  async pause(attemptId: number): Promise<Attempt> {
    const r = await api.post(`/exams/attempts/${attemptId}/pause/`, {});
    return parseAttempt(r.data, "POST pause");
  },

  async resumePause(attemptId: number): Promise<Attempt> {
    const r = await api.post(`/exams/attempts/${attemptId}/resume_pause/`, {});
    return parseAttempt(r.data, "POST resume_pause");
  },

  /** Submit the active module → advances state (M1→M2, or M2→SCORING). */
  async submitModule(
    attemptId: number,
    answers: Record<string, string>,
    flagged: number[],
    opts: MutationOptions = {},
  ): Promise<Attempt> {
    const r = await api.post(
      `/exams/attempts/${attemptId}/submit_module/`,
      withVersion({ answers, flagged }, opts.expectedVersionNumber),
      { headers: idemHeaders(opts.idempotencyKey) },
    );
    return parseAttempt(r.data, "POST submit_module");
  },

  /** Persist in-progress answers without advancing state (autosave). */
  async saveAttempt(
    attemptId: number,
    answers: Record<string, string>,
    flagged: number[],
    opts: MutationOptions = {},
  ): Promise<Attempt> {
    const r = await api.post(
      `/exams/attempts/${attemptId}/save_attempt/`,
      withVersion({ answers, flagged }, opts.expectedVersionNumber),
      { headers: idemHeaders(opts.idempotencyKey) },
    );
    return parseAttempt(r.data, "POST save_attempt");
  },
};

export type ExamApi = typeof examApi;
