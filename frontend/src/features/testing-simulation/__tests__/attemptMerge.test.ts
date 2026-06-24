import { describe, expect, it } from "vitest";
import { isActive, isCompleted, isScoring, mergeAttempt, shouldAccept } from "../state/attemptMerge";
import type { Attempt } from "../types";

/** Minimal Attempt factory — only the fields the merge guard reads. */
function makeAttempt(overrides: Partial<Attempt> = {}): Attempt {
  return {
    id: 1,
    current_state: "MODULE_1_ACTIVE",
    version_number: 1,
    practice_test_details: { id: 1, subject: "MATH", title: "T", modules: [] },
    current_module: 10,
    current_module_details: { id: 10, module_order: 1, time_limit_minutes: 35, questions: [] },
    current_module_start_time: "2026-01-01T00:00:00Z",
    server_now: "2026-01-01T00:00:00Z",
    remaining_seconds: 2100,
    module_duration_seconds: 2100,
    current_module_saved_answers: null,
    current_module_flagged_questions: null,
    is_completed: false,
    is_expired: false,
    is_paused: false,
    ...overrides,
  } as Attempt;
}

describe("shouldAccept — forward-only merge guard", () => {
  it("accepts the first snapshot", () => {
    expect(shouldAccept(null, makeAttempt())).toBe(true);
  });

  it("accepts a strictly newer version", () => {
    const prev = makeAttempt({ version_number: 3 });
    const next = makeAttempt({ version_number: 4 });
    expect(shouldAccept(prev, next)).toBe(true);
  });

  it("rejects an older version (stale in-flight poll)", () => {
    const prev = makeAttempt({ version_number: 5 });
    const next = makeAttempt({ version_number: 4 });
    expect(shouldAccept(prev, next)).toBe(false);
  });

  it("rejects a module-order regression while active (M2 → stale M1)", () => {
    const prev = makeAttempt({
      version_number: 5,
      current_state: "MODULE_2_ACTIVE",
      current_module_details: { id: 11, module_order: 2, time_limit_minutes: 35, questions: [] },
    });
    const staleM1 = makeAttempt({
      version_number: 5,
      current_state: "MODULE_1_ACTIVE",
      current_module_details: { id: 10, module_order: 1, time_limit_minutes: 35, questions: [] },
    });
    expect(shouldAccept(prev, staleM1)).toBe(false);
  });

  it("allows the move to SCORING/COMPLETED even though it has no active module", () => {
    const prev = makeAttempt({
      version_number: 5,
      current_state: "MODULE_2_ACTIVE",
      current_module_details: { id: 11, module_order: 2, time_limit_minutes: 35, questions: [] },
    });
    const scoring = makeAttempt({
      version_number: 6,
      current_state: "SCORING",
      current_module_details: null,
      is_completed: false,
    });
    expect(shouldAccept(prev, scoring)).toBe(true);
  });

  it("mergeAttempt keeps prev when the next is rejected", () => {
    const prev = makeAttempt({ version_number: 9 });
    const next = makeAttempt({ version_number: 2 });
    expect(mergeAttempt(prev, next)).toBe(prev);
  });
});

describe("lifecycle predicates", () => {
  it("isActive covers both active modules", () => {
    expect(isActive(makeAttempt({ current_state: "MODULE_1_ACTIVE" }))).toBe(true);
    expect(isActive(makeAttempt({ current_state: "MODULE_2_ACTIVE" }))).toBe(true);
    expect(isActive(makeAttempt({ current_state: "SCORING" }))).toBe(false);
  });

  it("isScoring / isCompleted are exact", () => {
    expect(isScoring(makeAttempt({ current_state: "SCORING" }))).toBe(true);
    expect(isCompleted(makeAttempt({ current_state: "COMPLETED", is_completed: true }))).toBe(true);
    expect(isCompleted(makeAttempt({ current_state: "COMPLETED", is_completed: false }))).toBe(false);
  });
});
