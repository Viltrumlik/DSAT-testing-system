import { prepareRichText } from "@/components/MathText";
import { renderMathInString } from "@/lib/mathRender";

/**
 * renderExamHtml — render authored question content to HTML using the SAME
 * pipeline as MathText (the review page and Content Studio author preview).
 *
 * Question content is authored in the Content Studio textarea (see
 * FormulaToolbar): markdown bold/italic (`**b**`, `*i*`), `<u>`/`<sup>`/`<sub>`,
 * and KaTeX LaTeX delimiters (`\( \)`, `\[ \]`, `$…$`, `$$…$$`). The Testing
 * Simulation renders that content through SafeHtml (so the offset-based
 * highlighter can wrap DOM ranges in <mark>), but SafeHtml is a raw HTML
 * passthrough: it does NOT convert markdown, and its MathJax typeset is a no-op
 * because MathJax is never loaded on this surface. The result was literal
 * "**bold**" text and LaTeX that rendered only via a fragile body-walk.
 *
 *   prepareRichText    -> sanitize, newline-to-break, markdown bold/italic to HTML
 *   renderMathInString -> KaTeX-render every delimiter into the string
 *
 * The output is handed to SafeHtml; DOMPurify preserves the KaTeX spans and the
 * formatting tags. This makes the student question view render identically to
 * the review/solution and admin-preview surfaces, which already use MathText.
 *
 * This composition is byte-identical to MathText's own internal render
 * expression, so the two surfaces stay in lockstep.
 */
export function renderExamHtml(raw: string | null | undefined): string {
  return renderMathInString(prepareRichText(raw ?? ""));
}
