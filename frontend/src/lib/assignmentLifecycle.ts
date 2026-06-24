/**
 * Assignment Lifecycle Utilities
 *
 * Derives operational lifecycle states for assignments from backend-provided
 * fields.  The backend does not expose an explicit `state` enum for assignments;
 * lifecycle is inferred from timing and submission activity.
 *
 * These states differ by content type in their educational meaning but share
 * the same temporal derivation rules:
 *
 *   Assessment homework → pedagogical lifecycle (has grading semantics)
 *   Mock exam           → simulation lifecycle  (has benchmark semantics)
 *   Pastpaper           → practice lifecycle    (has review semantics)
 *   Midterm             → evaluation lifecycle  (has formal grading semantics)
 *
 * The states below describe OPERATIONAL status only — what an operator
 * needs to act on — not educational outcome.
 */

// ─── State type ──────────────────────────────────────────────────────────────

/**
 * Lifecycle states for assignments.
 * Derived from `due_at`, `submissions_count`, and optionally `visible_from`.
 *
 * NOT backed by a backend enum — derived purely on the client.
 */
export type AssignmentLifecycleState =
  /**
   * `visible_from` is set to a future date — the assignment exists but is not
   * yet visible to students. Teacher/admin only.
   */
  | "SCHEDULED"
  /** Has a future due date more than 48 hours away; accepting submissions. */
  | "ACTIVE"
  /** Due within the next 48 hours. Needs teacher/admin attention. */
  | "DUE_SOON"
  /** Past the due date with zero or no recorded submissions. Intervention needed. */
  | "OVERDUE"
  /**
   * Past due AND has submissions recorded.
   * Operationally: submission window has closed; results can be reviewed.
   */
  | "COMPLETED"
  /**
   * No due_at set, no submissions recorded.
   * The assignment is technically open with no time pressure.
   */
  | "NO_DEADLINE";

// ─── Configuration ───────────────────────────────────────────────────────────

/** Hours before due_at at which state transitions from ACTIVE → DUE_SOON */
const DUE_SOON_HORIZON_HOURS = 48;

// ─── Derivation ──────────────────────────────────────────────────────────────

/**
 * Derive assignment lifecycle state from observable backend fields.
 *
 * @param assignment - Partial assignment shape; only timing/count fields used.
 */
export function deriveAssignmentLifecycleState(assignment: {
  due_at?: string | null;
  submissions_count?: number | null;
  /** Optional: ISO string. If in the future, the assignment is SCHEDULED (not yet visible to students). */
  visible_from?: string | null;
}): AssignmentLifecycleState {
  const now = Date.now();

  // SCHEDULED: exists but not yet released to students
  if (assignment.visible_from) {
    const visibleMs = new Date(assignment.visible_from).getTime();
    if (visibleMs > now) return "SCHEDULED";
  }

  const dueMs = assignment.due_at ? new Date(assignment.due_at).getTime() : null;
  const submissions = assignment.submissions_count ?? 0;

  if (dueMs === null) {
    // No deadline — perpetually open
    return "NO_DEADLINE";
  }

  const msUntilDue = dueMs - now;

  if (msUntilDue < 0) {
    // Past deadline
    return submissions > 0 ? "COMPLETED" : "OVERDUE";
  }

  if (msUntilDue < DUE_SOON_HORIZON_HOURS * 60 * 60 * 1000) {
    return "DUE_SOON";
  }

  return "ACTIVE";
}

// ─── Priority ordering ───────────────────────────────────────────────────────

/**
 * Urgency priority for sorting/ranking.
 * Lower number = higher urgency = shown first in operational views.
 */
export const LIFECYCLE_PRIORITY: Record<AssignmentLifecycleState, number> = {
  OVERDUE: 0,
  DUE_SOON: 1,
  ACTIVE: 2,
  COMPLETED: 3,
  NO_DEADLINE: 4,
  SCHEDULED: 5, // Lowest urgency — not yet visible to students
};

/** Sort assignments by operational urgency (most urgent first). */
export function sortByLifecyclePriority<
  T extends { due_at?: string | null; submissions_count?: number | null },
>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const pa = LIFECYCLE_PRIORITY[deriveAssignmentLifecycleState(a)];
    const pb = LIFECYCLE_PRIORITY[deriveAssignmentLifecycleState(b)];
    if (pa !== pb) return pa - pb;
    // Within same state: sort by due_at ascending (soonest first)
    const da = a.due_at ? new Date(a.due_at).getTime() : Infinity;
    const db = b.due_at ? new Date(b.due_at).getTime() : Infinity;
    return da - db;
  });
}

// ─── Display helpers ─────────────────────────────────────────────────────────

type LifecycleSpec = {
  label: string;
  description: string;
  /** Tailwind classes for the badge */
  badgeClasses: string;
  /** Whether this state requires operator attention */
  needsAttention: boolean;
};

export const LIFECYCLE_DISPLAY: Record<AssignmentLifecycleState, LifecycleSpec> = {
  SCHEDULED: {
    label: "Scheduled",
    description: "Not yet visible to students. Will release automatically.",
    badgeClasses: "bg-violet-100 text-violet-700",
    needsAttention: false,
  },
  ACTIVE: {
    label: "Active",
    description: "Accepting submissions. Due in more than 48 hours.",
    badgeClasses: "bg-emerald-100 text-emerald-800",
    needsAttention: false,
  },
  DUE_SOON: {
    label: "Due soon",
    description: "Due within 48 hours. Ensure students are aware.",
    badgeClasses: "bg-orange-100 text-orange-800",
    needsAttention: true,
  },
  OVERDUE: {
    label: "Overdue",
    description: "Past deadline with no submissions. Consider extending or closing.",
    badgeClasses: "bg-red-100 text-red-800",
    needsAttention: true,
  },
  COMPLETED: {
    label: "Completed",
    description: "Past deadline. Submissions recorded — ready for review.",
    badgeClasses: "bg-teal-100 text-teal-800",
    needsAttention: false,
  },
  NO_DEADLINE: {
    label: "Open",
    description: "No deadline set. Accepting submissions indefinitely.",
    badgeClasses: "bg-sky-100 text-sky-700",
    needsAttention: false,
  },
};

// ─── Aggregate helpers (for dashboard signals) ────────────────────────────────

type AssignmentInput = {
  due_at?: string | null;
  submissions_count?: number | null;
};

export type AssignmentLifecycleSummary = {
  total: number;
  scheduled: number;
  overdue: number;
  dueSoon: number;
  active: number;
  completed: number;
  noDeadline: number;
  needsAttention: number;
};

/** Aggregate lifecycle counts across an array of assignments. */
export function summarizeAssignmentLifecycle(
  assignments: AssignmentInput[],
): AssignmentLifecycleSummary {
  const counts = { scheduled: 0, overdue: 0, dueSoon: 0, active: 0, completed: 0, noDeadline: 0 };
  for (const a of assignments) {
    const state = deriveAssignmentLifecycleState(a);
    if (state === "SCHEDULED") counts.scheduled++;
    else if (state === "OVERDUE") counts.overdue++;
    else if (state === "DUE_SOON") counts.dueSoon++;
    else if (state === "ACTIVE") counts.active++;
    else if (state === "COMPLETED") counts.completed++;
    else counts.noDeadline++;
  }
  return {
    total: assignments.length,
    ...counts,
    needsAttention: counts.overdue + counts.dueSoon,
  };
}

// ─── Time helpers ────────────────────────────────────────────────────────────

/**
 * Returns a compact, human-readable time-until/time-since string.
 * Used in assignment list rows for the due date display.
 *
 * Examples:
 *   "due in 2 days"
 *   "due in 3 hours"
 *   "3 days overdue"
 *   "no deadline"
 */
export function formatAssignmentDue(due_at?: string | null): string {
  if (!due_at) return "no deadline";

  const now = Date.now();
  const dueMs = new Date(due_at).getTime();
  const diffMs = dueMs - now;
  const absMs = Math.abs(diffMs);

  const minutes = Math.floor(absMs / 60_000);
  const hours = Math.floor(absMs / 3_600_000);
  const days = Math.floor(absMs / 86_400_000);

  if (diffMs > 0) {
    // Future
    if (minutes < 60) return `due in ${minutes}m`;
    if (hours < 24) return `due in ${hours}h`;
    return `due in ${days}d`;
  } else {
    // Past
    if (minutes < 60) return `${minutes}m overdue`;
    if (hours < 24) return `${hours}h overdue`;
    return `${days}d overdue`;
  }
}

/**
 * Returns a precise formatted due date string for tooltips / detail views.
 */
export function formatAssignmentDueFull(due_at?: string | null): string {
  if (!due_at) return "No deadline";
  try {
    return new Date(due_at).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return due_at;
  }
}
