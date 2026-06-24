/**
 * Scratch-notes persistence. Notes are a study aid only — they are NEVER sent to
 * the backend and are completely independent of the exam engine/autosave.
 * Stored per attempt in localStorage.
 */
function key(attemptId: number | string): string {
  return `ts.notes.${attemptId}`;
}

export function readNotes(attemptId: number | string): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(key(attemptId)) ?? "";
  } catch {
    return "";
  }
}

export function writeNotes(attemptId: number | string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key(attemptId), value);
  } catch {
    /* ignore quota / private mode */
  }
}
