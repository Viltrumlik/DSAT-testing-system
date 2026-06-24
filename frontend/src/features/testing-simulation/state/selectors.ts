/** Derived read-only views over an Attempt. Pure functions, no React. */
import type { Attempt, ExamQuestion, ExamSubjectKind } from "../types";

const RW = ["READING", "WRITING", "READING_WRITING", "READING AND WRITING", "ENGLISH", "RW", "VERBAL"];
const MATH = ["MATH", "MATHEMATICS"];

function norm(s: string | null | undefined): string {
  return (s ?? "").trim().toUpperCase().replace(/[_\s]+/g, " ");
}

export function subjectKind(attempt: Attempt | null): ExamSubjectKind {
  const s = norm(attempt?.practice_test_details?.subject);
  if (MATH.some((m) => s.includes(m))) return "MATH";
  if (RW.some((r) => s.includes(r.replace(/_/g, " ")))) return "READING_WRITING";
  // Default to RW layout (two-pane) when ambiguous.
  return "READING_WRITING";
}

export const isMath = (a: Attempt | null): boolean => subjectKind(a) === "MATH";
export const isReadingWriting = (a: Attempt | null): boolean => subjectKind(a) === "READING_WRITING";

export function questions(attempt: Attempt | null): ExamQuestion[] {
  return attempt?.current_module_details?.questions ?? [];
}

export function moduleLabel(attempt: Attempt | null): string {
  const order = attempt?.current_module_details?.module_order ?? 1;
  const subject = subjectKind(attempt) === "MATH" ? "Math" : "Reading and Writing";
  const section = subjectKind(attempt) === "MATH" ? 2 : 1;
  return `Section ${section}, Module ${order}: ${subject}`;
}

/** Whether this attempt allows manual pause (pastpapers yes, mocks no). */
export function pauseAllowed(attempt: Attempt | null, mockFlow: boolean): boolean {
  return !mockFlow && attempt?.practice_test_details?.mock_kind !== "MIDTERM";
}
