/** Admin question row from GET …/modules/:moduleId/questions/ */
export type AdminModuleQuestion = {
  id: number;
  module_id?: number;
  practice_test_id?: number;
  order: number;
  question_text: string;
  question_prompt: string;
  question_type: "MATH" | "READING" | "WRITING";
  is_math_input: boolean;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  /** Serialised as `correct_answer` from backend (maps to `correct_answers` field). */
  correct_answer: string;
  explanation: string;
  score: number;
  question_image?: string | null;
  option_a_image?: string | null;
  option_b_image?: string | null;
  option_c_image?: string | null;
  option_d_image?: string | null;
};
