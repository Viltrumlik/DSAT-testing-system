/**
 * Offline-safe local draft of per-module work. This is a *backup* for the
 * server's `current_module_saved_answers`; the server is always authoritative.
 * Scoped by (attempt, module) so Module 1 work can never bleed into Module 2.
 */
import { z } from "zod";

const draftSchema = z.object({
  answers: z.record(z.string(), z.string()),
  flagged: z.array(z.number()),
  version: z.number().nullable(),
  moduleId: z.number(),
});
export type ExamDraft = z.infer<typeof draftSchema>;

function key(attemptId: number | string, moduleId: number): string {
  return `ts.draft.${attemptId}.${moduleId}`;
}

export function readDraft(attemptId: number | string, moduleId: number): ExamDraft | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key(attemptId, moduleId));
    if (!raw) return null;
    const parsed = draftSchema.safeParse(JSON.parse(raw));
    return parsed.success && parsed.data.moduleId === moduleId ? parsed.data : null;
  } catch {
    return null;
  }
}

export function writeDraft(attemptId: number | string, draft: ExamDraft): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key(attemptId, draft.moduleId), JSON.stringify(draft));
  } catch {
    /* quota / private mode — ignore, server is the source of truth */
  }
}

export function clearDraft(attemptId: number | string, moduleId: number): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(key(attemptId, moduleId));
  } catch {
    /* ignore */
  }
}
