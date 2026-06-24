import Cookies from "js-cookie";

function readMeCookie(): Record<string, unknown> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = Cookies.get("lms_user");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * UI-only permission helpers (menu visibility, labels). The backend enforces all authorization on every API.
 * Never use these values as a security gate. Derived from GET `/users/me/` (cached in `lms_user` by `useMe`).
 */
export function getPermissionList(): string[] {
  if (typeof window === "undefined") return [];
  const me = readMeCookie();
  const p = me?.permissions;
  if (Array.isArray(p)) {
    return p.filter((x): x is string => typeof x === "string");
  }
  return [];
}

/** Single domain subject for staff (math | english), derived from `/users/me/` (via lms_user cookie cache). */
export function getSubject(): "math" | "english" | null {
  if (typeof window === "undefined") return null;
  const raw = String(readMeCookie()?.subject || "").trim().toLowerCase();
  if (raw === "math" || raw === "english") return raw;
  return null;
}

/** Role derived from `/users/me/` (via `lms_user` cache synced from the API). */
export function getRole(): string {
  if (typeof window === "undefined") return "";
  const me = readMeCookie();
  return me?.role ? String(me.role).trim().toLowerCase() : "";
}

/** Role is test_admin (backend: global test library staff). */
export function isTestAdmin(): boolean {
  return getRole() === "test_admin";
}

/**
 * Matches backend `/api/exams/admin` — any non-student may create/edit/delete tests and questions.
 * Use so test_admin (often no `lms_subject`) and staff without granular `lms_permissions` still get UI affordances.
 */
export function canManageQuestionsConsole(): boolean {
  if (can("*")) return true;
  const r = getRole();
  return (
    r === "super_admin" ||
    r === "admin" ||
    r === "test_admin"
  );
}

/** Prefer this in admin UI over `can("manage_tests")` alone — includes staff roles when cookies omit codenames. */
export function canAuthorTestsUi(): boolean {
  return canManageQuestionsConsole() || can("manage_tests");
}

/**
 * Normalize practice-test platform subject from API (handles stray casing/whitespace).
 */
export function normalizePlatformSubject(raw: string | null | undefined): "READING_WRITING" | "MATH" | null {
  if (raw == null || raw === "") return null;
  let s = String(raw).trim();
  if (typeof s.normalize === "function") {
    s = s.normalize("NFKC");
  }
  // Zero-width / BOM from copy-paste or bad exports — breaks strict === "MATH" in filters.
  s = s.replace(/[\u200B-\u200D\uFEFF]/g, "").trim();
  if (!s) return null;
  const u = s.toUpperCase().replace(/\s+/g, "_");
  // Canonical platform enums + common API/legacy variants (never rely on strict === in UI).
  if (u === "MATH" || u === "MATHEMATICS" || u === "MATHS") return "MATH";
  if (
    u === "READING_WRITING" ||
    u === "RW" ||
    u === "READING" ||
    u === "WRITING" ||
    u === "ENGLISH" ||
    u === "R&W" ||
    u === "R_AND_W"
  ) {
    return "READING_WRITING";
  }
  // Display-style labels from bad imports / manual DB edits
  if (u.includes("READING") && u.includes("WRITING")) return "READING_WRITING";
  // Locale / human labels (serializer or CMS) — R&W often still matches heuristics; Math needs explicit help.
  const low = s.toLowerCase();
  if (
    low === "math" ||
    low === "mathematics" ||
    low === "maths"
  ) {
    return "MATH";
  }
  if (low.includes("reading") && low.includes("writing")) return "READING_WRITING";
  return null;
}

export function platformSubjectIsMath(raw: string | null | undefined): boolean {
  if (normalizePlatformSubject(raw) === "MATH") return true;
  // Last resort: model value from DB is exactly "MATH" but odd invisible chars slipped past normalize.
  const s = String(raw ?? "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim()
    .toUpperCase();
  return s === "MATH";
}

export function platformSubjectIsReadingWriting(raw: string | null | undefined): boolean {
  if (normalizePlatformSubject(raw) === "READING_WRITING") return true;
  const s = String(raw ?? "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim()
    .toUpperCase();
  return s === "READING_WRITING";
}

/** First non-empty subject-like field on a PracticeTest row (defensive against odd API shapes). */
export function practiceTestRowSubject(row: any): string | undefined {
  if (row == null || typeof row !== "object") return undefined;
  const keys = ["subject", "platform_subject", "section_subject", "exam_subject"] as const;
  for (const k of keys) {
    const v = row[k];
    if (v != null && String(v).trim() !== "") return String(v);
  }
  return undefined;
}

/** API may return a single object instead of a one-element array; normalize for list UIs. */
export function coalesceArray<T>(x: T | T[] | null | undefined): T[] {
  if (x == null) return [];
  return Array.isArray(x) ? x : [x];
}

export function can(codename: string): boolean {
  const p = getPermissionList();
  if (p.includes("*")) return true;

  // Accept both canonical and legacy codenames transparently.
  const aliases: Record<string, string[]> = {
    // Canonical -> legacy equivalents
    assign_access: ["manage_roles", "assign_test_access"],
    create_classroom: ["manage_classrooms"],
    manage_tests: [
      "view_all_tests",
      "view_english_tests",
      "view_math_tests",
      "create_test",
      "edit_test",
      "delete_test",
      "create_mock_sat",
      "create_midterm_mock",
    ],
    manage_users: ["access_lms_admin"],

    // Legacy -> canonical equivalents (UI often calls can("edit_test") etc.)
    manage_roles: ["assign_access"],
    assign_test_access: ["assign_access"],
    manage_classrooms: ["create_classroom"],
    access_lms_admin: ["manage_users"],
    view_all_tests: ["manage_tests"],
    view_english_tests: ["manage_tests"],
    view_math_tests: ["manage_tests"],
    create_test: ["manage_tests"],
    edit_test: ["manage_tests"],
    delete_test: ["manage_tests"],
    create_mock_sat: ["manage_tests"],
    create_midterm_mock: ["manage_tests"],
  };

  const checks = new Set<string>([codename, ...(aliases[codename] || [])]);
  for (const c of checks) {
    if (p.includes(c)) return true;
  }
  return false;
}

/** Timed mock / questions authoring surfaces (mocks, sections, modules). */
export function canManageMockExamShell(): boolean {
  return can("*") || canManageQuestionsConsole() || can("manage_tests");
}

/**
 * Subject-scoped visibility for tests (mirrors backend scope enforcement).
 * Platform English tests use subject READING_WRITING, scope key is "english".
 */
export function canAbacTestSubject(subject: string): boolean {
  if (can("*")) return true;
  const p = normalizePlatformSubject(subject);
  if (!p) return false;
  const dom = getSubject();
  if (!dom) return false;
  if (p === "READING_WRITING") return dom === "english";
  if (p === "MATH") return dom === "math";
  return false;
}

/** Default pastpaper bulk-assign subject filter: scoped admins start on their subject only. */
export function defaultBulkPastpaperSubjectScope(): "BOTH" | "MATH" | "READING_WRITING" {
  if (can("*")) return "BOTH";
  const dom = getSubject();
  if (dom === "math") return "MATH";
  if (dom === "english") return "READING_WRITING";
  return "BOTH";
}

export function canCreateTestForSubject(subject: "READING_WRITING" | "MATH"): boolean {
  if (canManageQuestionsConsole()) return true;
  return can("manage_tests") && canAbacTestSubject(subject);
}

export function canEditQuestionsForSubject(subject: string | undefined): boolean {
  if (canManageQuestionsConsole()) return true;
  if (!subject) return false;
  return can("manage_tests") && canAbacTestSubject(subject);
}

export function canDeletePracticeTestFromMock(subject: string | undefined): boolean {
  if (canManageQuestionsConsole()) return true;
  if (!subject) return false;
  return can("manage_tests") && canAbacTestSubject(subject);
}

/** Global Questions admin tab (not midterm-only flows). */
export function canUseGlobalQuestionsTab(): boolean {
  return can("*") || canManageQuestionsConsole() || can("manage_tests");
}
