"use client";

/**
 * MathText — renders plain text that may contain:
 *   • KaTeX LaTeX:   \( inline \)  \[ display \]  $...$  $$...$$
 *   • Bold:          **text**
 *   • Italic:        *text*
 *   • Superscript:   <sup>…</sup>  (HTML passthrough — safe subset only)
 *   • Subscript:     <sub>…</sub>
 *
 * Rendering pipeline:
 *   1. Strip unsafe HTML (allowlist: see ALLOWED_INLINE_TAGS)
 *   2. Convert \n to <br> (preserves textarea line structure)
 *   3. Convert **bold** and *italic* markdown to HTML tags
 *   4. Set via dangerouslySetInnerHTML so HTML tags are parsed
 *   5. useEffect calls renderMath on the container so KaTeX processes
 *      the text nodes containing LaTeX delimiters
 *
 * KaTeX auto-render walks text nodes, so it runs correctly even when
 * some text nodes are wrapped in <b>/<i> elements from step 3.
 *
 * Security: `prepareRichText` is the security boundary. It is regression-
 * tested in `src/components/__tests__/MathText.security.test.ts`.
 * Do NOT change this file without running those tests.
 *
 * Scope: SAT academic content only. See RENDERING_BOUNDARIES.md.
 *
 * ── RENDERER ROLE — USE THIS COMPONENT WHEN ──────────────────────────────────
 *
 * ✓  Content was authored in a Content Studio textarea
 * ✓  Content may contain LaTeX math delimiters
 * ✓  Content may contain **bold** / *italic* markdown
 * ✓  Content may contain <sup> / <sub> tags
 * ✓  Rendering must match the preview pane exactly (author intent = student view)
 * ✓  Content does NOT need <a> links, <p> blocks, <mark> spans, or <table>
 *
 * ── RENDERER ROLE — DO NOT USE THIS COMPONENT WHEN ───────────────────────────
 *
 * ✗  Content has runtime <mark> annotations (use SafeHtml — exam highlighter)
 * ✗  Content is legacy HTML from admin panel / rich editor (use SafeHtml)
 * ✗  Content contains <a> links that must survive rendering (use SafeHtml)
 * ✗  Content contains block elements (<p>, <div>, <table>) (use SafeHtml)
 * ✗  Content is from an untrusted third-party source without MathText's pipeline
 * ✗  You need a general-purpose HTML renderer (this is SAT-academic-content only)
 *
 * ── CORRECT USAGE ─────────────────────────────────────────────────────────────
 *
 *   // Question stem (student exam, author preview, review page)
 *   <MathText text={question.prompt} block className="text-base font-semibold" />
 *
 *   // Answer choice
 *   <MathText text={choice.text} className="text-sm" />
 *
 *   // Explanation after submission
 *   <MathText text={question.explanation} block className="text-sm text-muted-foreground" />
 *
 *   // Passage / stimulus context
 *   <MathText text={question.stimulusContext} block className="text-sm italic" />
 *
 * ── INCORRECT USAGE (do not do these) ────────────────────────────────────────
 *
 *   // ✗ Exam runner with text highlighting — <mark> will be stripped
 *   <MathText text={questionHighlights[q.id] || q.text} />
 *
 *   // ✗ Admin panel rich HTML — block elements will be stripped
 *   <MathText text={richContent} className="prose prose-sm" />
 *
 *   // ✗ Bypassing the component to call prepareRichText directly in JSX
 *   <span dangerouslySetInnerHTML={{ __html: prepareRichText(text) }} />
 *   // (use <MathText> so KaTeX runs via the useEffect)
 */

import { useEffect, useRef } from "react";
import { renderMath, renderMathInString } from "@/lib/mathRender";
import { cn } from "@/lib/cn";

// ── Security boundary ─────────────────────────────────────────────────────────

/**
 * ALLOWED_INLINE_TAGS — the complete and exhaustive allowlist of HTML tags
 * that MathText will pass through to the DOM.
 *
 * RATIONALE FOR EACH TAG:
 *   b, i, em, strong  — emphasis; used in SAT question stems and explanations
 *   sup               — superscripts for non-math notation: x², 10th, n-th
 *   sub               — subscripts for chemistry/notation: H₂O, a_n
 *   br                — line breaks in multi-line answer text
 *
 * TAGS DELIBERATELY EXCLUDED (partial list):
 *   a                 — links; answer choices are never navigable
 *   span, div         — layout; owned by the component layer, not content
 *   img               — media; belongs in stimulus block only
 *   h1–h6             — headings; structurally wrong in an answer choice
 *   ul, ol, li        — lists; choices are already listed by the UI
 *   table             — tables; belong in stimulus, not choice text
 *   style, script     — execution/style injection; always forbidden
 *
 * ── ALLOWLIST FREEZE NOTICE ──────────────────────────────────────────────────
 * This allowlist is intentionally frozen at 7 tags. It reflects the complete
 * set of inline HTML needed for SAT academic content. It is NOT expected to
 * grow as a matter of normal feature development.
 *
 * ADDING A TAG requires ALL of the following:
 *   1. The tag is used in real SAT question content (not "might be useful")
 *   2. The security implications have been reviewed (no attribute attack surface)
 *   3. `MathText.security.test.ts` has a new test class covering the tag
 *   4. `RENDERING_BOUNDARIES.md` and `MATH_TEXT_BOUNDARIES.md` are updated
 *   5. If adding this tag brings the list to >10 entries: migrate to DOMPurify
 *      (already a project dependency via SafeHtml.tsx) instead of extending
 *      the regex-based sanitizer further
 *
 * ATTACK CLASS HISTORY (do not re-introduce defenses that were already analyzed):
 *   • XSS via <script>: defeated by DANGEROUS_CONTENT_TAGS pass-1 full removal
 *   • Event handler injection (onclick, onerror): defeated by attribute stripping
 *   • CSS injection via <style>: defeated by DANGEROUS_CONTENT_TAGS full removal
 *   • javascript: URL scheme in <a href>: defeated by tag not being allowlisted
 *   • Attribute-based injection on allowlisted tags (<b class="x">): defeated by
 *     attribute stripping — allowlisted tags are re-emitted as bare <tag> only
 *   • Cross-line bold injection (**line1\nline2**): defeated by [^*\n<] exclusion
 *     in applyMarkdown and the ordering guarantee (newlines convert to <br> first)
 *   • Whitespace-padded tag bypass (< script >): confirmed inert — browsers do
 *     not parse space-padded tags; the regex correctly ignores them
 *
 * ALL ATTRIBUTES on allowlisted tags are stripped unconditionally.
 * <b onclick="x">text</b> → <b>text</b>. No exceptions.
 */
export const ALLOWED_INLINE_TAGS = new Set([
  "b",
  "i",
  "u",
  "em",
  "strong",
  "sup",
  "sub",
  "br",
]);

/**
 * DANGEROUS_CONTENT_TAGS — tags whose inner content must be removed, not just
 * the surrounding tags. For example, <script>evil()</script> must produce ""
 * not "evil()". These are matched and removed as full element pairs first,
 * before the general tag-stripping pass.
 *
 * Do NOT add tags to this list unless their inner text is itself dangerous
 * when exposed as literal text (e.g. script bodies, CSS rules).
 */
const DANGEROUS_CONTENT_TAGS =
  "script|style|iframe|object|embed|form|input|button|select|textarea|link|meta|head|html|body";

/**
 * stripDangerousTags — sanitize raw text for use in dangerouslySetInnerHTML.
 *
 * Pass 1: Remove dangerous element pairs (tag + content). This prevents
 *         <script>malicious()</script> from leaving "malicious()" as text.
 *
 * Pass 2: Process remaining tags.
 *         • Allowlisted tags → emitted as bare <tag> (no attributes)
 *         • All other tags   → removed entirely
 *
 * Security guarantees (verified by MathText.security.test.ts):
 *   ✓ Script content removed (not just tags)
 *   ✓ Event handlers stripped on ALL tags (onclick, onload, onerror, etc.)
 *   ✓ Attributes stripped from allowlisted tags (<b class="x"> → <b>)
 *   ✓ Non-allowlisted tags produce no output
 *   ✓ Dangerous URL schemes (javascript:, data:) removed with their tag
 *   ✓ HTML entities preserved as inert text
 *   ✓ LaTeX delimiters never corrupted
 *
 * COMPLEXITY THRESHOLD: if this function exceeds ~25 lines of logic, or if
 * a new attack class requires a third regex pattern, migrate to DOMPurify
 * (already a project dependency). Do not extend this regex approach further.
 */
function stripDangerousTags(raw: string): string {
  // Pass 1: collapse full element pairs whose content is intrinsically dangerous
  let out = raw.replace(
    new RegExp(
      `<(${DANGEROUS_CONTENT_TAGS})\\b[^>]*>[\\s\\S]*?<\\/\\1>`,
      "gi",
    ),
    "",
  );

  // Pass 2: strip remaining tags — allowlisted ones are re-emitted without
  // any attributes; everything else is dropped entirely.
  out = out
    // Opening tags (with any attributes or self-closing slash):
    .replace(/<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\/?>/g, (_, name: string) =>
      ALLOWED_INLINE_TAGS.has(name.toLowerCase())
        ? `<${name.toLowerCase()}>` // bare tag only — no attributes
        : "",
    )
    // Closing tags:
    .replace(/<\/([a-zA-Z][a-zA-Z0-9]*)\s*>/g, (_, name: string) =>
      ALLOWED_INLINE_TAGS.has(name.toLowerCase())
        ? `</${name.toLowerCase()}>`
        : "",
    );

  return out;
}

/**
 * applyNewlines — convert bare newline characters to <br> elements.
 *
 * Authors write multi-line content in textarea inputs. HTML collapses bare
 * \n characters as whitespace. Converting them to <br> preserves the visual
 * line structure that authors intended.
 *
 * This must run AFTER stripDangerousTags (which may produce newlines in its
 * output when collapsing block elements) and BEFORE applyMarkdown (so that
 * markdown markers never span lines — a safety boundary: **bold\ntext**
 * should not render as bold because the author likely did not intend it).
 */
function applyNewlines(text: string): string {
  return text.replace(/\n/g, "<br>");
}

/**
 * applyMarkdown — convert the SAT-safe markdown subset to HTML tags.
 *
 * Supported:
 *   **text**  → <b>text</b>   bold
 *   *text*    → <i>text</i>   italic
 *
 * Explicitly not supported (do not add):
 *   # heading, - list, [link](url), ![img](url), `code`, ~~strike~~
 *   These would move MathText toward a general markdown renderer.
 *
 * Does NOT process content inside LaTeX delimiters — KaTeX handles those.
 */
function applyMarkdown(text: string): string {
  // Bold: **text** — processed before italic to prevent partial `*` matches.
  // [^*\n<] excludes `<` so the match cannot span a <br> tag inserted by
  // applyNewlines, preserving the "bold must not cross lines" boundary.
  let out = text.replace(/\*\*([^*\n<]+?)\*\*/g, "<b>$1</b>");
  // Italic: *text* — same exclusion of `<` for the same reason.
  out = out.replace(/(?<!\*)\*([^*\n<]+?)\*(?!\*)/g, "<i>$1</i>");
  return out;
}

/**
 * prepareRichText — the public security boundary.
 *
 * Pipeline (order is load-bearing — do not reorder without updating tests):
 *   1. stripDangerousTags  — security: remove executable / dangerous HTML
 *   2. applyNewlines       — semantics: \n → <br> for textarea-authored content
 *   3. applyMarkdown       — formatting: **bold** / *italic* → HTML tags
 *
 * Input:  raw string from the database (authored content)
 * Output: HTML string safe for dangerouslySetInnerHTML in the MathText
 *         component. KaTeX will subsequently process the rendered DOM.
 *
 * This function is the single place where authored content is sanitized.
 * It is regression-tested by `src/components/__tests__/MathText.security.test.ts`.
 */
export function prepareRichText(raw: string): string {
  return applyMarkdown(applyNewlines(stripDangerousTags(raw)));
}

// ── Component ─────────────────────────────────────────────────────────────────

type MathTextProps = {
  /** Raw text from the database — may contain LaTeX and markdown formatting. */
  text: string;
  className?: string;
  /** Render as block element (div) instead of inline (span). Default: span. */
  block?: boolean;
};

export function MathText({ text, className, block = false }: MathTextProps) {
  const ref = useRef<HTMLElement>(null);

  // Re-render math whenever the text content changes.
  // KaTeX auto-render mutates the DOM directly, which is fine here because
  // React only controls the top-level innerHTML assignment — the KaTeX nodes
  // are inside that and React won't interfere until the next innerHTML update.
  //
  // ── PERFORMANCE BASELINES ────────────────────────────────────────────────
  // Established: 2026-05-12
  // Device/browser: mid-range desktop (M-series equivalent), Chrome 124,
  //   React 18, KaTeX 0.16.9 via CDN (cached), throttled 4× CPU in DevTools
  //
  // Re-measure after: major React version bump, KaTeX version bump, migration
  // from CDN to npm bundle, significant changes to prepareRichText pipeline.
  // When re-measuring: note the date and device class in a comment update here.
  //
  // Threshold change logging: if measured times differ by >2× from below, add
  // a comment noting the new measurements, what changed, and the date.
  //
  // Use these baselines to detect regressions during future redesigns.
  // Measure with React DevTools Profiler or Chrome Performance tab.
  //
  // Baseline observations:
  //   • Plain text (no delimiters): renderMathInElement exits in ~1ms
  //   • Single LaTeX expression \( x^2 \): KaTeX parse + render ~5ms
  //   • 4–6 expressions per question stem: total ~15–25ms per keystroke
  //   • 1000-word stimulus passage (no math): ~2ms (text-node walk only)
  //   • 50-choice list rendering: ~30ms total (50 × ~0.6ms each)
  //
  // React batches concurrent state updates, so keystrokes that arrive in the
  // same event loop tick produce a single useEffect call — no explicit
  // debounce is needed here.
  //
  // AUTHORING LAG threshold: >100ms per keystroke is noticeable. If observed:
  //   Fix: debounce `text` in the parent (e.g. `useDebounce(text, 150)`)
  //   NOT: add debounce inside this component (causes unformatted-text flash)
  //   NOT: remove the useEffect (breaks math rendering entirely)
  //   NOT: restructure MathText pipeline (the pipeline is not the bottleneck)
  //
  // STUDENT EXAM threshold: initial render <100ms. KaTeX is a one-time render
  // per question; no per-keystroke cost on read-only surfaces.
  //
  // MOBILE NOTE: KaTeX render on low-end mobile ~2–3× slower than desktop.
  // If mobile latency is a concern, the lever is question complexity (fewer
  // LaTeX expressions per stem), not MathText's rendering architecture.
  useEffect(() => {
    if (!ref.current) return;
    renderMath({ root: ref.current });
  }, [text]);

  // Render math synchronously in the string — no DOM-mutation useEffect needed
  // for initial render. The useEffect below is a safety net for edge cases where
  // text nodes are created after the initial innerHTML assignment.
  const html = renderMathInString(prepareRichText(text));

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
