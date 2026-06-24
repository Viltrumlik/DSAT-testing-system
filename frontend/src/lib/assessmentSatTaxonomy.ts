/**
 * Official-style Reading & Writing and Math domains for LMS assessment sets.
 * Stored value is `"{domain} › {subdomain}"` (single-character separator U+203A).
 */

export type AssessmentSubjectKey = "english" | "math";

export type SatCategoryGroup = {
  domain: string;
  subdomains: readonly string[];
};

/** Reading & Writing — domains and subdomains (Digital SAT skill alignment). */
export const READING_WRITING_SAT_GROUPS: readonly SatCategoryGroup[] = [
  {
    domain: "Craft and Structure",
    subdomains: ["Cross-Text Connections", "Text Structure and Purpose", "Words in Context"],
  },
  {
    domain: "Expression of Ideas",
    subdomains: ["Rhetorical Synthesis", "Transitions"],
  },
  {
    domain: "Information and Ideas",
    subdomains: ["Central Ideas and Details", "Command of Evidence", "Inferences"],
  },
  {
    domain: "Standard English Conventions",
    subdomains: ["Boundaries", "Form, Structure, and Sense"],
  },
] as const;

/** Math — domains and subdomains. */
export const MATH_SAT_GROUPS: readonly SatCategoryGroup[] = [
  {
    domain: "Algebra",
    subdomains: [
      "Linear equations in one variable",
      "Linear functions",
      "Linear equations in two variables",
      "Systems of two linear equations in two variables",
      "Linear inequalities in one or two variables",
    ],
  },
  {
    domain: "Advanced Math",
    subdomains: [
      "Equivalent expressions",
      "Nonlinear equations in one variable and systems of equations in two variables",
      "Nonlinear functions",
    ],
  },
  {
    domain: "Problem-Solving and Data Analysis",
    subdomains: [
      "Ratios, rates, proportional relationships, and units",
      "Percentages",
      "One-variable data: Distributions and measures of center and spread",
      "Two-variable data: Models and scatterplots",
      "Probability and conditional probability",
      "Inference from sample statistics and margin of error",
      "Evaluating statistical claims: Observational studies and experiments",
    ],
  },
  {
    domain: "Geometry and Trigonometry",
    subdomains: [
      "Area and volume",
      "Lines, angles, and triangles",
      "Right triangles and trigonometry",
      "Circles",
    ],
  },
] as const;

const SEP = " › ";

export function formatAssessmentCategoryValue(domain: string, subdomain: string): string {
  return `${domain.trim()}${SEP}${subdomain.trim()}`;
}

export function assessmentCategoryGroups(subject: AssessmentSubjectKey): readonly SatCategoryGroup[] {
  return subject === "math" ? MATH_SAT_GROUPS : READING_WRITING_SAT_GROUPS;
}

export function allAssessmentCategoryValues(subject: AssessmentSubjectKey): string[] {
  const out: string[] = [];
  for (const g of assessmentCategoryGroups(subject)) {
    for (const s of g.subdomains) {
      out.push(formatAssessmentCategoryValue(g.domain, s));
    }
  }
  return out;
}

export function isKnownAssessmentCategory(subject: AssessmentSubjectKey, value: string): boolean {
  const v = value.trim();
  if (!v) return true;
  return allAssessmentCategoryValues(subject).includes(v);
}
