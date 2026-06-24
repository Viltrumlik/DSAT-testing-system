/** Deterministic idempotency keys so retries never double-apply a mutation. */

function randomSegment(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Start key, persisted per attempt so a refresh during start reuses the same
 * key and the backend dedupes instead of starting twice.
 */
export function startKey(attemptId: number): string {
  const storageKey = `ts.idem.start.${attemptId}`;
  if (typeof window !== "undefined") {
    try {
      const existing = sessionStorage.getItem(storageKey);
      if (existing) return existing;
      const fresh = `start.${attemptId}.${randomSegment()}`;
      sessionStorage.setItem(storageKey, fresh);
      return fresh;
    } catch {
      /* fall through */
    }
  }
  return `start.${attemptId}.${randomSegment()}`;
}

/**
 * Submit key is derived from (attempt, module, version) so an automatic retry
 * of the *same* submit is idempotent, but a genuine new submit gets a new key.
 */
export function submitKey(attemptId: number, moduleId: number, version: number, suffix = ""): string {
  return `submit.${attemptId}.${moduleId}.v${version}${suffix ? `.${suffix}` : ""}`;
}

export function saveKey(attemptId: number, moduleId: number, version: number): string {
  return `save.${attemptId}.${moduleId}.v${version}`;
}
