/**
 * Annotation persistence — per (attempt, question, container), in localStorage.
 * Purely a study annotation; independent of the exam engine, never synced.
 *
 * A "container" is a highlightable region (passage / question / choices), each
 * with its own character-offset space, so the same question can carry separate
 * annotations on its passage, prompt and answer choices.
 *
 * Stored under `ts.annot.<attempt>.<question>.<container>`. On read, the
 * passage container migrates forward any legacy single-region data
 * (`ts.annot.<attempt>.<question>` and the older `ts.hl.<...>` shape).
 */
import { type Annotation, mergeAnnotations } from "./annotations";

function key(attemptId: number | string, questionId: number, container: string): string {
  return `ts.annot.${attemptId}.${questionId}.${container}`;
}

function isAnnotation(v: unknown): v is Annotation {
  if (!v || typeof v !== "object") return false;
  const a = v as Record<string, unknown>;
  return (
    typeof a.start === "number" &&
    typeof a.end === "number" &&
    a.end > a.start &&
    (a.kind === "highlight" || a.kind === "underline")
  );
}

/** Convert legacy `{start,end,style}` ranges to the new Annotation shape. */
function migrateLegacy(raw: unknown): Annotation[] {
  if (!Array.isArray(raw)) return [];
  const out: Annotation[] = [];
  for (const r of raw) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    if (typeof o.start !== "number" || typeof o.end !== "number" || o.end <= o.start) continue;
    if (o.kind === "highlight" || o.kind === "underline") {
      out.push(o as unknown as Annotation);
    } else if (o.style === "blue" || o.style === "pink" || o.style === "yellow") {
      out.push({ start: o.start, end: o.end, kind: "highlight", color: o.style });
    } else if (o.style === "underline") {
      out.push({ start: o.start, end: o.end, kind: "underline", underline: "solid" });
    } else {
      out.push({ start: o.start, end: o.end, kind: "highlight", color: "yellow" });
    }
  }
  return out;
}

function readKey(k: string): Annotation[] | null {
  try {
    const raw = localStorage.getItem(k);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? mergeAnnotations(parsed.filter(isAnnotation)) : [];
  } catch {
    return null;
  }
}

export function readAnnotations(attemptId: number | string, questionId: number, container: string): Annotation[] {
  if (typeof window === "undefined") return [];
  const direct = readKey(key(attemptId, questionId, container));
  if (direct) return direct;
  // Passage migrates legacy single-region data once.
  if (container === "passage") {
    try {
      const legacy =
        localStorage.getItem(`ts.annot.${attemptId}.${questionId}`) ??
        localStorage.getItem(`ts.hl.${attemptId}.${questionId}`);
      if (legacy) {
        const migrated = mergeAnnotations(migrateLegacy(JSON.parse(legacy)));
        if (migrated.length) writeAnnotations(attemptId, questionId, container, migrated);
        return migrated;
      }
    } catch {
      /* ignore */
    }
  }
  return [];
}

export function writeAnnotations(
  attemptId: number | string,
  questionId: number,
  container: string,
  anns: Annotation[],
): Annotation[] {
  const merged = mergeAnnotations(anns);
  if (typeof window !== "undefined") {
    try {
      if (merged.length === 0) localStorage.removeItem(key(attemptId, questionId, container));
      else localStorage.setItem(key(attemptId, questionId, container), JSON.stringify(merged));
    } catch {
      /* ignore quota / unavailable */
    }
  }
  return merged;
}
