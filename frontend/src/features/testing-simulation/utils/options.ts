/** Answer-option parsing. Options may be a string map or a `{ text, image }` map. */
import type { ExamQuestion } from "../types";

export interface ParsedOption {
  key: string;
  text: string;
  image?: string;
}

function entryText(val: unknown): string {
  if (typeof val === "string") return val;
  if (val && typeof val === "object" && "text" in val && typeof (val as { text?: unknown }).text === "string") {
    return (val as { text: string }).text;
  }
  return "";
}

function entryImage(val: unknown): string | undefined {
  if (val && typeof val === "object" && "image" in val && typeof (val as { image?: unknown }).image === "string") {
    return (val as { image: string }).image;
  }
  return undefined;
}

const DEFAULT_KEYS = ["A", "B", "C", "D"] as const;

/** Normalize a question's options into an ordered list, defaulting to A–D. */
export function parseOptions(question: ExamQuestion): ParsedOption[] {
  const opts = question.options;
  if (opts && typeof opts === "object" && !Array.isArray(opts)) {
    return Object.entries(opts as Record<string, unknown>).map(([key, val]) => ({
      key,
      text: entryText(val),
      image: entryImage(val),
    }));
  }
  return DEFAULT_KEYS.map((key) => ({ key, text: "" }));
}
