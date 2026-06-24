import type { ExamQuestion } from "../types";

/**
 * Student-Produced Response (SPR / grid-in / open response) detection.
 *
 * In this engine the wire flag is `is_math_input` — the same flag `AnswerPane`
 * uses to render the numeric `SprInput` instead of the `ChoiceList`. SPR
 * questions are the only ones that show the Student-Produced Response Directions
 * panel; multiple-choice (math or RW) and passage questions never do.
 */
export function isStudentProducedResponse(q: ExamQuestion | null | undefined): boolean {
  return Boolean(q?.is_math_input);
}
