"use client";

/**
 * SafeHtml — renders arbitrary HTML with DOMPurify sanitization + MathJax math.
 *
 * ── LONG-TERM ARCHITECTURAL POSITIONING ──────────────────────────────────────
 *
 * Two surfaces currently depend on this component. Their long-term roles differ:
 *
 * SURFACE A — Legacy exam runner (exam/[attemptId]/page.tsx)
 * Architectural status: PERMANENT SPECIALIZED RENDERER (Option A)
 *
 *   The text-highlighting feature stores annotated HTML with <mark> spans in
 *   component state. `MathText`'s strict allowlist unconditionally strips <mark>.
 *   This is not a timing problem or a missing migration step — it is a
 *   structural mismatch between how the two renderers work.
 *
 *   `SafeHtml` is the correct renderer for this surface indefinitely, until
 *   AND UNLESS the highlighting system is fundamentally redesigned to store
 *   selection offsets instead of HTML mutations (see RENDERING_BOUNDARIES.md
 *   Phase 2). Even after that redesign, the exam page may still need SafeHtml
 *   for edge cases (e.g., passage HTML from external content providers).
 *
 *   Decision: do NOT treat the exam surface as a migration target without first
 *   redesigning the highlight storage model. The surface is not temporary.
 *
 * SURFACE B — Legacy admin panel (admin/page.tsx)
 * Architectural status: LEGACY BRIDGE — no migration planned
 *
 *   The admin panel predates the Content Studio and uses a separate rendering
 *   system (MathJax + MathRenderer + rich-text editor toolbar). It is not
 *   student-facing and is lower priority for convergence.
 *
 *   This is a legacy bridge: it exists because migrating the admin surface to
 *   MathText would require re-authoring all existing admin content, replacing
 *   MathJax with KaTeX, and rebuilding the editor toolbar. There is no plan to
 *   do this. The surface is stable, not actively drifting.
 *
 *   Decision: admin surface remains on SafeHtml indefinitely. Do not invest
 *   migration effort here until the exam surface is fully resolved.
 *
 * SUMMARY
 *   • `SafeHtml` is not a transitional shim. It is purpose-built for surfaces
 *     with runtime-mutated HTML (highlighting) and legacy rich-HTML content.
 *   • The decision to retire `SafeHtml` does not exist on any roadmap.
 *   • New surfaces must not use `SafeHtml` — use `MathText` instead.
 *
 * ── OWNERSHIP STATEMENT ───────────────────────────────────────────────────────
 *
 * This component is INTENTIONALLY RETAINED infrastructure. It is NOT a
 * legacy artifact awaiting deletion. It serves surfaces that require HTML
 * semantics that `MathText` deliberately does not support.
 *
 * DO NOT replace SafeHtml with MathText without first verifying that the
 * consuming surface no longer needs any of the capabilities listed below.
 *
 * ── WHY IT STILL EXISTS ───────────────────────────────────────────────────────
 *
 * `MathText` enforces a strict 7-tag allowlist (b, i, em, strong, sup, sub,
 * br) and processes authored textarea content through a deterministic
 * pipeline. That constraint is a feature, not a deficiency — it is the
 * security and semantic contract that makes `MathText` trustworthy for SAT
 * academic content.
 *
 * `SafeHtml` exists for surfaces whose content:
 *   1. Was NOT authored in the Content Studio textarea model
 *   2. Requires HTML elements outside the `MathText` allowlist to function
 *   3. Is already structured as rich HTML from a different authoring system
 *
 * ── SURFACES THAT DEPEND ON SAFEHTML ─────────────────────────────────────────
 *
 * | Surface                          | File                         | Why SafeHtml is required                          |
 * |----------------------------------|------------------------------|---------------------------------------------------|
 * | Legacy exam runner — question    | app/exam/[attemptId]/page.tsx | Text-highlight feature stores annotated HTML      |
 * | Legacy exam runner — choices     | app/exam/[attemptId]/page.tsx | with <mark> spans in component state.             |
 * |                                  |                              | MathText's allowlist strips <mark> unconditionally|
 * | Legacy admin panel — content     | app/admin/page.tsx           | Rich prose editor with its own toolbar; uses      |
 * | Legacy admin panel — MathPreview | app/admin/page.tsx           | MathJax hybrid; separate rendering system.        |
 *
 * See RENDERING_BOUNDARIES.md for the complete surface inventory and the
 * test ("does this need arbitrary HTML?") for deciding which renderer to use.
 *
 * ── WHAT SAFEHTML UNIQUELY SUPPORTS ──────────────────────────────────────────
 *
 * • `<mark>` — runtime text highlighting applied programmatically in state.
 *   The legacy exam runner highlights selected words by mutating the HTML
 *   string, inserting `<mark>` spans around selection offsets. This is the
 *   primary reason the exam page cannot use `MathText` today.
 *
 * • `<a>`, `<p>`, `<div>`, `<table>`, `<ul>`, `<li>`, `<h1>`–`<h6>` —
 *   broad HTML passthrough for legacy CMS / admin-panel prose content.
 *
 * • MathJax rendering — the admin panel predates KaTeX adoption. SafeHtml
 *   calls `MathJax.typesetPromise` so legacy content with `\( \)` notation
 *   renders without re-authoring. MathText uses KaTeX; these are not the
 *   same renderer and are not interchangeable.
 *
 * • DOMPurify default allowlist (~80 tags) — more permissive than MathText's
 *   7-tag allowlist, appropriate for the legacy admin surface.
 *
 * ── WHY MATHTEXT CANNOT REPLACE SAFEHTML TODAY ───────────────────────────────
 *
 * 1. `<mark>` is unconditionally stripped by MathText's allowlist. The exam
 *    runner's text-highlighting feature writes `<mark>` into the HTML string
 *    in state on every highlight action. Replacing SafeHtml would silently
 *    destroy that feature.
 *
 * 2. The admin panel uses MathJax (loaded as a global script). Switching to
 *    MathText would require migrating all existing admin content to KaTeX
 *    delimiter syntax and removing the MathJax dependency — a separate
 *    project-scope decision.
 *
 * ── FUTURE CONVERGENCE REQUIREMENTS ──────────────────────────────────────────
 *
 * To migrate the legacy exam runner off SafeHtml (see RENDERING_BOUNDARIES.md
 * Phase 2):
 *   1. Replace HTML-mutation highlight storage with character-offset storage.
 *      Instead of `html = html.replace(selectedText, '<mark>'+selectedText+'</mark>')`,
 *      store `{ start: number, end: number }[]` alongside base text.
 *   2. Render base text with `MathText`.
 *   3. Apply highlights as an overlay: CSS Highlight API, or absolutely-
 *      positioned overlay elements keyed by offset.
 *   Do NOT attempt this migration without completing step 1 first.
 *
 * To migrate the admin panel off SafeHtml: out of scope — admin is not
 * student-facing, migration is lower priority than exam runner.
 *
 * ── RENDERER ROLE — USE THIS COMPONENT WHEN ─────────────────────────────────
 *
 * ✓  Content has runtime <mark> annotation (e.g. exam text-highlighting)
 * ✓  Content contains <a> links that must survive rendering
 * ✓  Content contains block elements (<p>, <div>, <table>) from a CMS/editor
 * ✓  Content was authored in a legacy rich-text editor with full HTML output
 * ✓  Content predates the Content Studio textarea model
 *
 * ── RENDERER ROLE — DO NOT USE THIS COMPONENT WHEN ───────────────────────────
 *
 * ✗  Content was authored in the Content Studio textarea (use MathText)
 * ✗  Content is a SAT question stem, answer choice, or explanation (use MathText)
 * ✗  Content may contain LaTeX and you need guaranteed KaTeX rendering (use MathText)
 * ✗  You are building a new student-facing or author-facing surface (use MathText)
 * ✗  You want to render **bold** / *italic* textarea markdown (use MathText)
 *
 * When in doubt: if the content was typed into a Content Studio textarea,
 * use MathText. SafeHtml is for the surfaces listed above only.
 *
 * ── SCOPE FREEZE ─────────────────────────────────────────────────────────────
 *
 * SafeHtml is a SPECIALIZED component. Its approved surface count is currently 4.
 * That count must ONLY DECREASE over time (via migration), never increase.
 *
 * Explicitly FORBIDDEN expansions — do not use SafeHtml for:
 *
 *   ✗  Any new student-facing content surface
 *      (students expect KaTeX math rendering; SafeHtml uses MathJax which may
 *       not be loaded on student-facing pages)
 *
 *   ✗  Any new author-facing content surface
 *      (authors need MathText for preview-parity with the student view)
 *
 *   ✗  Formatting convenience: "SafeHtml is easier because it passes HTML through"
 *      (this is the single most likely source of renderer sprawl)
 *
 *   ✗  New question stems, answer choices, explanations, or stimuli
 *      (these are Content Studio content — they are MathText territory)
 *
 *   ✗  New admin sub-features that don't share the legacy admin content model
 *      (the admin exception is for the existing rich-text editor, not for
 *       new admin panels that should use the Content Studio model)
 *
 * ── REJECTED USE CASES (for institutional memory) ────────────────────────────
 *
 * These are concrete use cases that were considered and explicitly rejected:
 *
 *   ✗  Student analytics panel with formatted text
 *      Rejected: analytics content is not highlight-mutable or legacy-HTML;
 *      use MathText for any math content in analytics, plain text otherwise.
 *
 *   ✗  New results page showing question summaries
 *      Rejected: question text is Content Studio content; the review page
 *      already demonstrates the correct pattern — use MathText.
 *
 *   ✗  A "rich announcement banner" for students with formatted HTML from admin
 *      Rejected: announcement content does not contain <mark> mutations or
 *      MathJax-rendered legacy math; a banner component that renders plain
 *      text or MathText is sufficient and semantically correct.
 *
 *   ✗  Rendering explanation text in a sidebar widget
 *      Rejected: explanation text is authored Content Studio content;
 *      sidebar context does not change the content class; use MathText.
 *
 * Adding a new SafeHtml surface requires: a governance review, an explicit
 * architectural justification, and a new entry in RENDERER_OWNERSHIP_INDEX.md
 * explaining why MathText cannot serve the surface. The bar is high — the
 * surface must have a structural reason MathText fails (e.g., runtime HTML
 * mutation), not just a convenience reason (e.g., "it already has HTML").
 *
 * ── MIGRATION MYTHS ───────────────────────────────────────────────────────────
 *
 * These are plausible-sounding migration arguments that are incorrect:
 *
 * Myth 1: "The review page migrated fine, so the exam page should too."
 *   Reality: The review page is READ-ONLY academic content. The exam page has
 *   a runtime highlight mutation system that writes `<mark>` tags into the HTML
 *   string. These are structurally different. The review page migration worked
 *   because it had no runtime mutations. The exam page requires redesigning the
 *   highlight storage model first. See Phase 2 in RENDERING_BOUNDARIES.md.
 *
 * Myth 2: "Just add `<mark>` to MathText's allowlist and the exam page can migrate."
 *   Reality: The exam highlighter doesn't just render `<mark>` — it WRITES `<mark>`
 *   into the HTML string in component state on every highlight action. MathText's
 *   `prepareRichText` pipeline is idempotent and runs on the stored authored text.
 *   Even if `<mark>` were allowlisted, the highlights would be stripped on the next
 *   re-render when `prepareRichText` runs on the un-marked base text.
 *
 * Myth 3: "DOMPurify is stricter than MathText's allowlist, so SafeHtml is safer."
 *   Reality: DOMPurify's DEFAULT settings allow ~80 tags including `<script>` (which
 *   it handles) but also `<form>`, `<input>`, and `<button>` which have non-obvious
 *   attack surfaces. MathText's 7-tag allowlist is MORE restrictive for the specific
 *   content class it serves. "More tags = less safe" for SAT academic content.
 *
 * ── NON-GOALS ─────────────────────────────────────────────────────────────────
 *
 * SafeHtml is NOT:
 *   - A general-purpose HTML renderer for any content that "happens to have HTML"
 *   - The "safe" version of MathText (MathText is also safe, differently scoped)
 *   - A fallback for when MathText's allowlist is too restrictive
 *   - A convenience option for surfaces that "already have HTML structure"
 *   - An upgrade path from MathText (they are peers, not a hierarchy)
 *
 * ── SECURITY MODEL ────────────────────────────────────────────────────────────
 *
 * DOMPurify default settings sanitize the input before it reaches the DOM.
 * This is a broad-spectrum sanitizer, not the narrow allowlist in MathText.
 * It is appropriate here because the consuming surfaces already accept
 * arbitrary HTML (the legacy admin and exam page were designed for rich HTML).
 *
 * If this component ever starts receiving student-authored input (not legacy
 * admin / exam content), re-evaluate whether DOMPurify defaults are
 * sufficiently restrictive for that content class.
 */

import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";

export default function SafeHtml({
  html,
  ...divProps
}: React.HTMLAttributes<HTMLDivElement> & { html: string }) {
  const safe = useMemo(() => DOMPurify.sanitize(html), [html]);
  const ref = useRef<HTMLDivElement | null>(null);

  // Write innerHTML ONLY when the sanitized HTML actually changes — never on an
  // unrelated parent re-render (e.g. the 1-second exam timer). `dangerouslySet-
  // InnerHTML` re-applies on every commit, which replaces the text nodes and so
  // (a) wipes runtime DOM mutations layered on top — the highlighter's <mark>
  // spans — and (b) collapses any in-progress text selection. Setting innerHTML
  // imperatively, keyed on `safe`, preserves both across re-renders. This is the
  // surface SafeHtml exists for (runtime-mutated highlight HTML).
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== safe) el.innerHTML = safe;
  }, [safe]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const w = window as unknown as {
      MathJax?: { typesetPromise?: (elements?: Element[]) => Promise<unknown> };
    };
    const typeset = w?.MathJax?.typesetPromise;
    if (typeof typeset !== "function") return;

    let cancelled = false;
    // Defer until DOM updates settle (helps after state changes).
    const raf = window.requestAnimationFrame(() => {
      if (cancelled) return;
      void typeset([el]).catch(() => {
        /* ignore MathJax errors; HTML still renders */
      });
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
    };
  }, [safe]);

  return <div ref={ref} {...divProps} suppressHydrationWarning />;
}
