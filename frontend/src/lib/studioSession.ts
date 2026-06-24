/**
 * studioSession — lightweight single-user session memory for the SAT Content Studio.
 *
 * SCOPE BOUNDARIES (intentional):
 *   ✓ Last edited assessment set + question
 *   ✓ Last edited pastpaper module
 *   ✓ Timestamp for staleness check
 *   ✗ Panel positions, scroll offsets, filter state
 *   ✗ Collaborative presence
 *   ✗ Full UI state snapshots
 *
 * The session key is versioned (v1). If the schema changes incompatibly,
 * bump the version suffix — old keys will be ignored and self-expire.
 *
 * localStorage is only available client-side. All reads are wrapped in
 * try/catch to handle private-browsing restrictions gracefully.
 */

const KEY = "studio_session_v1";

/** Maximum session age in milliseconds before the "continue" card is suppressed. */
const MAX_AGE_MS = 48 * 60 * 60 * 1000; // 48 hours

export type StudioSession = {
  /** The last assessment set the author had open in the editor. */
  lastSetId?: number;
  /** The last question selected within that set. */
  lastQuestionId?: number;
  /** The last pastpaper module (standalone section) the author had open. */
  lastPastpaperModule?: {
    testId: number;
    moduleId: number;
    /** Human-readable label e.g. "SAT Oct 2024 · Reading & Writing · Module 1" */
    label?: string;
  };
  /** ISO timestamp of the most recent session write. */
  updatedAt: string;
};

function isValid(raw: unknown): raw is StudioSession {
  return (
    typeof raw === "object" &&
    raw !== null &&
    typeof (raw as Record<string, unknown>).updatedAt === "string"
  );
}

/**
 * Read the current studio session from localStorage.
 * Returns null if no session exists, the session is malformed, or it is stale.
 */
export function readStudioSession(): StudioSession | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isValid(parsed)) return null;
    const age = Date.now() - new Date(parsed.updatedAt).getTime();
    if (age > MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Merge a partial update into the current studio session and persist it.
 * Always updates `updatedAt` to now.
 *
 * Safe to call from useEffect — localStorage writes are synchronous but
 * fast enough to be non-blocking in this context.
 */
export function writeStudioSession(patch: Omit<Partial<StudioSession>, "updatedAt">): void {
  try {
    const existing = readStudioSession() ?? ({} as Partial<StudioSession>);
    const next: StudioSession = {
      ...existing,
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage quota exceeded or private browsing — fail silently.
  }
}

/**
 * Clear the studio session entirely.
 * Call this on explicit "start fresh" actions, not on page navigation.
 */
export function clearStudioSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

/**
 * Derive a human-readable "Continue working on…" label from a session.
 * Returns null if the session has no actionable context.
 */
export function sessionContinueLabel(session: StudioSession): string | null {
  if (session.lastSetId) {
    return `Set #${session.lastSetId}${session.lastQuestionId ? ` · Q${session.lastQuestionId}` : ""}`;
  }
  if (session.lastPastpaperModule?.label) {
    return session.lastPastpaperModule.label;
  }
  if (session.lastPastpaperModule) {
    return `Module #${session.lastPastpaperModule.moduleId}`;
  }
  return null;
}

/**
 * Derive the URL to resume the session in the studio.
 * Returns null if no actionable route can be constructed.
 */
export function sessionContinueHref(session: StudioSession): string | null {
  if (session.lastSetId) {
    const base = `/builder/sets/${session.lastSetId}`;
    return session.lastQuestionId ? `${base}?questionId=${session.lastQuestionId}` : base;
  }
  if (session.lastPastpaperModule) {
    const { testId, moduleId } = session.lastPastpaperModule;
    return `/builder/pastpapers/${testId}/${moduleId}`;
  }
  return null;
}
