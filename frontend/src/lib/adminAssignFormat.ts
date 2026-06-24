import { normalizePlatformSubject } from "./permissions";

/** Normalize for duplicate checks and search. */
export function adminNorm(s: string) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function pastpaperPackSignatureFromForm(f: {
  title: string;
  practice_date: string;
  label: string;
  form_type: string;
}) {
  return `${adminNorm(f.title)}|${f.practice_date || ""}|${adminNorm(f.label)}|${f.form_type || "INTERNATIONAL"}`;
}

export function pastpaperPackSignatureFromPack(p: Record<string, unknown> | null | undefined) {
  return `${adminNorm(String(p?.title || ""))}|${String(p?.practice_date || "")}|${adminNorm(String(p?.label || ""))}|${String(p?.form_type || "INTERNATIONAL")}`;
}

/** One-line admin label: stable id + human title. */
export function formatPastpaperPackAdminLabel(p: Record<string, unknown> | null | undefined): string {
  const title = String(p?.title || "").trim();
  const date = String(p?.practice_date || "");
  const lbl = String(p?.label || "").trim();
  const ft = p?.form_type === "US" ? "US" : "Intl";
  const head = title || (date ? `Card ${date}` : `Pastpaper card`);
  const id = p?.id != null ? String(p.id) : "?";
  return `#${id} · ${head} · ${ft}${lbl ? ` · Form ${lbl}` : ""}${date && title ? ` · ${date}` : !title && date ? ` · ${date}` : ""}`;
}

export function formatMockExamAdminLabel(m: Record<string, unknown> | null | undefined): string {
  const title = String(m?.title || "").trim();
  const kind = m?.kind === "MIDTERM" ? "Midterm" : "SAT mock";
  const pub = m?.is_published ? "Live" : "Draft";
  const head = title || `Untitled`;
  const id = m?.id != null ? String(m.id) : "?";
  return `#${id} · ${head} · ${kind} · ${pub}${m?.practice_date ? ` · ${m.practice_date}` : ""}`;
}

export function pastpaperSectionSummary(sections: { subject?: string }[]): {
  hasRw: boolean;
  hasMath: boolean;
  n: number;
} {
  const hasRw = sections.some((s) => normalizePlatformSubject(s.subject) === "READING_WRITING");
  const hasMath = sections.some((s) => normalizePlatformSubject(s.subject) === "MATH");
  return { hasRw, hasMath, n: sections.length };
}

/** Pastpaper section row in admin assign UI. */
export function formatPastpaperSectionForAssign(t: Record<string, unknown>): string {
  const collection = String(t.collection_name ?? "").trim();
  const packHint = collection ? ` · ${collection}` : " · No collection";
  const subj = normalizePlatformSubject(String(t.subject ?? "")) === "MATH" ? "Math" : "R&W";
  const title = String(t.title || "").trim();
  const head = title || subj;
  const tid = t.id != null ? String(t.id) : "?";
  const label = t.label ? ` [${t.label}]` : "";
  return `#${tid} · ${head}${label}${packHint}`;
}
