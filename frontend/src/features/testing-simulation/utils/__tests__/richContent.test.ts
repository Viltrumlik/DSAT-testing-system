/**
 * richContent — regression coverage for Testing Simulation / Past Papers content.
 *
 * Bug: authored content (markdown bold/italic + KaTeX LaTeX, written in the
 * Content Studio textarea via FormulaToolbar) was rendered on the exam runner
 * through SafeHtml's raw passthrough — which does NOT convert markdown and whose
 * MathJax typeset is a no-op (MathJax is never loaded). Result: literal
 * "**bold**" and raw LaTeX, while review/solution and admin-preview (MathText)
 * rendered fine.
 *
 * Fix: render base content through `renderExamHtml`, i.e.
 * `renderMathInString(prepareRichText(text))` — the same expression MathText
 * uses internally. These tests lock the reported symptoms and the parity.
 */

import { describe, it, expect } from "vitest";
import { prepareRichText } from "@/components/MathText";
import { renderMathInString } from "@/lib/mathRender";
import { renderExamHtml } from "../richContent";

describe("renderExamHtml — exam-runner content rendering", () => {
  it("converts **bold** markdown to a <b> tag (was rendering literally)", () => {
    const out = renderExamHtml("The word **mass** matters.");
    expect(out).toContain("<b>mass</b>");
    expect(out).not.toContain("**mass**");
  });

  it("converts *italic* markdown to an <i> tag (was rendering literally)", () => {
    const out = renderExamHtml("Read *carefully* now.");
    expect(out).toContain("<i>carefully</i>");
    expect(out).not.toMatch(/\*carefully\*/);
  });

  it("preserves <u> underline authored by the toolbar", () => {
    expect(renderExamHtml("an <u>important</u> term")).toContain("<u>important</u>");
  });

  it("renders inline \\( … \\) LaTeX into KaTeX HTML (was raw text)", () => {
    const out = renderExamHtml("Solve \\(x^2 + 1 = 0\\) for x.");
    expect(out).toContain("katex");
    expect(out).not.toContain("\\(");
  });

  it("renders $…$ inline and $$…$$ display LaTeX", () => {
    expect(renderExamHtml("value $a+b$ here")).toContain("katex");
    expect(renderExamHtml("$$\\frac{a}{b}$$")).toContain("katex-display");
  });

  it("handles mixed markdown + math in one string", () => {
    const out = renderExamHtml("**Note:** the slope is \\(m = 2\\).");
    expect(out).toContain("<b>Note:</b>");
    expect(out).toContain("katex");
  });

  it("converts newlines to <br> (textarea-authored line breaks)", () => {
    expect(renderExamHtml("line one\nline two")).toContain("<br>");
  });

  it("is byte-identical to the MathText render expression (surface parity)", () => {
    const samples = [
      "**bold** and *italic*",
      "Solve \\(x^2\\) then $y$",
      "$$\\sqrt{x}$$",
      "plain text only",
    ];
    for (const s of samples) {
      expect(renderExamHtml(s)).toBe(renderMathInString(prepareRichText(s)));
    }
  });

  it("tolerates null/undefined content without throwing", () => {
    expect(renderExamHtml(null)).toBe("");
    expect(renderExamHtml(undefined)).toBe("");
  });
});
