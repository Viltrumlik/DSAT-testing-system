export * from "./attempt";

/** Subject helpers — the runner only needs the RW vs Math distinction for layout. */
export type ExamSubjectKind = "READING_WRITING" | "MATH";

/** Local-only UI view state for a single question, never sent to the server. */
export interface QuestionUiState {
  /** Selected option key ("A".."D") or SPR text. */
  answer?: string;
  /** Option keys the student crossed out. */
  eliminated: string[];
}
