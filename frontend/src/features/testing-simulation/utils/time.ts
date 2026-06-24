/** Time helpers for the server-anchored exam timer. Pure, no React, unit-testable. */

/** Format whole seconds as `M:SS` (Bluebook style). */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Resolve the module's wall-clock limit in seconds. Prefers the explicit
 * server-provided duration; falls back to the module's minute limit.
 */
export function moduleLimitSeconds(input: {
  module_duration_seconds: number | null;
  time_limit_minutes: number | null | undefined;
}): number {
  if (input.module_duration_seconds != null && Number.isFinite(input.module_duration_seconds)) {
    return Math.max(0, Math.floor(input.module_duration_seconds));
  }
  return Math.max(0, Math.floor((input.time_limit_minutes ?? 0) * 60));
}

/** Five-minute warning threshold, in seconds. */
export const FIVE_MINUTE_WARNING_SECONDS = 300;
