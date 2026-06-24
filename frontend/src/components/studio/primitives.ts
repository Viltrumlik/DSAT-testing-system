/**
 * Studio Primitives — canonical class token strings for the SAT Content Studio.
 *
 * RULE: Every authoring surface MUST import these tokens rather than declaring
 * local variants. Drift between surfaces begins the moment a second definition
 * appears. If you need a different visual treatment, justify it here.
 *
 * Adding a variant: extend the export list with a clearly named constant.
 * Do NOT create parallel local definitions in consuming files.
 */

// ─── Form field label ────────────────────────────────────────────────────────
/**
 * Canonical uppercase section label used above form inputs in all editor panels.
 * Apply via: <label className={STUDIO_FIELD_LABEL}>Field name</label>
 */
export const STUDIO_FIELD_LABEL =
  "mb-1 block text-[11px] font-bold text-muted-foreground uppercase tracking-widest";

// ─── Form input ───────────────────────────────────────────────────────────────
/**
 * Canonical text input / textarea / select class string for studio edit forms.
 * Apply via: <input className={STUDIO_INPUT} />
 *
 * Note: BuilderSetEditorContainer uses a distinct variant (bg-background, py-2.5,
 * shadow-sm) intentionally — the center panel editor has a different visual depth.
 * Do not merge those without an explicit design decision.
 */
export const STUDIO_INPUT =
  "w-full rounded-xl border border-border bg-surface-2/60 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none";

// ─── Section rhythm ───────────────────────────────────────────────────────────
/**
 * Standard vertical spacing between top-level sections on studio pages.
 */
export const STUDIO_SECTION_GAP = "space-y-5";

/**
 * Standard card container — rounded, bordered, on the card background.
 */
export const STUDIO_CARD =
  "overflow-hidden rounded-2xl border border-border bg-card shadow-sm";

// ─── Action hierarchy ─────────────────────────────────────────────────────────
/**
 * Primary CTA button — use for the single most important action per surface.
 */
export const STUDIO_BTN_PRIMARY =
  "inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors";

/**
 * Secondary / ghost button — for auxiliary actions alongside a primary CTA.
 */
export const STUDIO_BTN_SECONDARY =
  "inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-4 py-2 text-sm font-bold text-foreground hover:bg-surface-2 disabled:opacity-50 transition-colors";

/**
 * Destructive action button — delete, archive. Requires confirm step before use.
 */
export const STUDIO_BTN_DESTRUCTIVE =
  "inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-50 transition-colors";

// ─── Error banner ─────────────────────────────────────────────────────────────
/**
 * Inline error strip — shown below actions that fail (not full-page errors).
 */
export const STUDIO_ERROR_BANNER =
  "rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700";
