"use client";

/**
 * assessmentText — the single instructional-content rendering path for
 * pedagogical assessment surfaces (runner, review, retry).
 *
 * It deliberately REUSES the SAT rendering pipeline rather than duplicating it:
 *   • `prepareRichText`     — the MathText security boundary (sanitize + markdown)
 *   • `renderMathInString`  — KaTeX string rendering (same as MathText)
 *   • `renderMath`          — KaTeX DOM pass for text nodes created after mount
 *
 * The ONLY thing it adds on top of MathText is fill-in-the-blank rendering:
 * runs of underscores authored in English questions (`____`) are turned into a
 * real underline blank (see `.ms-blank` in globals.css) instead of leaving the
 * literal underscore glyphs, which read as broken on screen and on mobile.
 *
 * Boundary: this is instructional (classroom) content. It does NOT carry SAT
 * runtime semantics (no <mark> annotation persistence, no exam highlighter).
 * For the SAT exam highlighter, see SafeHtml / the exam runner.
 */

import { useEffect, useRef } from "react";
import DOMPurify from "dompurify";
import { prepareRichText } from "@/components/MathText";
import { renderMath, renderMathInString } from "@/lib/mathRender";
import { cn } from "@/lib/cn";

/**
 * Convert a run of 2+ underscores into a styled blank. Wrapping the underscores
 * (rather than replacing them) preserves the author-controlled blank length —
 * `.ms-blank` hides the glyphs and draws a clean baseline rule of that width.
 */
export function applyBlanks(text: string): string {
  return text.replace(/_{2,}/g, (run) => `<span class="ms-blank">${run}</span>`);
}

/**
 * processInstructionalText — string → HTML for assessment content.
 *
 * Order is load-bearing and mirrors MathText's pipeline:
 *   1. prepareRichText     — sanitize, newline-to-break, bold/italic markdown
 *   2. applyBlanks         — runs of underscores to an underline blank span
 *   3. renderMathInString  — LaTeX delimiters to KaTeX HTML
 *
 * Blanks are applied AFTER prepareRichText so the injected <span> survives the
 * sanitizer (it is not present when sanitization runs) and BEFORE KaTeX so the
 * span is never inserted inside a rendered formula.
 */
export function processInstructionalText(raw: string): string {
  return renderMathInString(applyBlanks(prepareRichText(raw)));
}

type AssessmentTextProps = {
  text: string;
  className?: string;
  /** Render as a block element (div) instead of inline-block (span). */
  block?: boolean;
};

/**
 * AssessmentText — drop-in renderer for instructional content. Mirrors the
 * MathText component contract (ref + useEffect KaTeX pass keyed on text) so
 * math, markdown, and blanks render identically to the assessment runner.
 */
export function AssessmentText({ text, className, block = false }: AssessmentTextProps) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (ref.current) renderMath({ root: ref.current });
  }, [text]);

  const html = processInstructionalText(text);

  if (block) {
    return (
      <div
        ref={ref as React.RefObject<HTMLDivElement>}
        className={cn("leading-relaxed", className)}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }
  return (
    <span
      ref={ref as React.RefObject<HTMLSpanElement>}
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── Highlight (annotation) primitives ─────────────────────────────────────────
// The assessment runner stores highlights as the post-KaTeX innerHTML of the
// question/passage container — i.e. text + rendered math + <mark> spans. These
// helpers are the single sanitize/render path for that saved HTML, shared by the
// interactive runner and the read-only review page so neither duplicates a
// highlight pipeline. This is instructional highlighting, NOT the SAT exam
// annotation system (SafeHtml / exam runner) — keep them separate.

/**
 * sanitizeHighlightHtml — sanitize saved highlight HTML while preserving the
 * <mark> annotations (with their inline colour styles/classes) and the KaTeX
 * span markup. Used wherever stored highlight HTML is rendered.
 */
export function sanitizeHighlightHtml(html: string): string {
  return DOMPurify.sanitize(html, { ADD_TAGS: ["mark"], ADD_ATTR: ["style", "class"] });
}

type HighlightedTextProps = {
  /** Saved highlight HTML (post-KaTeX innerHTML containing <mark> spans). */
  html: string;
  className?: string;
};

/**
 * HighlightedText — read-only renderer for saved highlight HTML. Sanitizes via
 * sanitizeHighlightHtml and runs a KaTeX pass as a safety net (idempotent: it
 * skips already-rendered .katex nodes) in case the HTML was captured before math
 * rendered. Used by the pedagogical review page to show retained highlights.
 */
export function HighlightedText({ html, className }: HighlightedTextProps) {
  const ref = useRef<HTMLDivElement>(null);
  const safe = sanitizeHighlightHtml(html);
  useEffect(() => {
    if (ref.current) renderMath({ root: ref.current });
  }, [safe]);
  return (
    <div
      ref={ref}
      className={cn("leading-relaxed", className)}
      dangerouslySetInnerHTML={{ __html: safe }}
    />
  );
}
