/**
 * Pure attempt-merge rules. The runner polls the backend from several places
 * (active poll, scoring poll, submit response, pause/resume). A slow in-flight
 * response can arrive *after* a newer one. These guards guarantee state only
 * ever moves forward — never regresses to a stale snapshot.
 *
 * Pure and side-effect free so it can be unit-tested in isolation.
 */
import { type Attempt, ATTEMPT_STATE } from "../types";

function moduleOrder(a: Attempt | null): number {
  const o = a?.current_module_details?.module_order;
  return o != null ? Number(o) : 0;
}

/**
 * Decide whether `next` should replace `prev`.
 * Rules:
 *  - No previous → accept.
 *  - Lower version → reject (older snapshot).
 *  - Module-order regression while still active → reject (stale module poll).
 *    (SCORING / COMPLETED legitimately have no active module, so they're exempt.)
 */
export function shouldAccept(prev: Attempt | null, next: Attempt): boolean {
  if (!prev) return true;
  if (next.version_number < prev.version_number) return false;

  const prevOrder = moduleOrder(prev);
  const nextOrder = moduleOrder(next);
  if (prevOrder > 0 && nextOrder > 0 && nextOrder < prevOrder && !next.is_completed) {
    return false;
  }
  return true;
}

/** Apply the merge rules, returning the snapshot that should be kept. */
export function mergeAttempt(prev: Attempt | null, next: Attempt): Attempt {
  return shouldAccept(prev, next) ? next : (prev as Attempt);
}

export const isActive = (a: Attempt | null): boolean =>
  a?.current_state === ATTEMPT_STATE.MODULE_1_ACTIVE || a?.current_state === ATTEMPT_STATE.MODULE_2_ACTIVE;

export const isScoring = (a: Attempt | null): boolean => a?.current_state === ATTEMPT_STATE.SCORING;

export const isCompleted = (a: Attempt | null): boolean =>
  a?.current_state === ATTEMPT_STATE.COMPLETED && Boolean(a?.is_completed);

export const isTerminal = (a: Attempt | null): boolean => isScoring(a) || isCompleted(a);

/** True when the engine says active but the module payload is missing (error state). */
export const isModulePayloadMissing = (a: Attempt | null): boolean =>
  isActive(a) && !a?.current_module_details;
