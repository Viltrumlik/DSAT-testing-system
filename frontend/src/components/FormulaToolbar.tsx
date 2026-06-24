"use client";

/**
 * FormulaToolbar — LaTeX snippet insertion toolbar for question authoring.
 *
 * Layout:
 *   1. Quick row — always-visible buttons for the 14 most-used symbols
 *      (π, √, ×, ÷, ±, ≤, ≥, ≠, ∞, °, x², ½, ≈, Δ)
 *   2. Category tabs + grid — full categorised library for less-common symbols
 *
 * Design contract:
 *   • Never steals textarea/input focus. All buttons use `onPointerDown` +
 *     `e.preventDefault()` so the browser never fires a blur on the active
 *     field before the click is processed.
 *   • Calls `onInsert(snippet, cursorOffset)` — the parent is responsible for
 *     reading `selectionStart/End`, splicing the snippet, updating React state,
 *     and restoring focus + cursor via `requestAnimationFrame`.
 *   • Shows rendered KaTeX in each button via MathText (span variant — valid
 *     inside <button>). KaTeX is synchronous; 8–12 renders per group view is
 *     well within the ~5ms-per-expression baseline.
 *
 * Usage:
 *   <FormulaToolbar onInsert={(snippet, cursorOffset) => { ... }} />
 */

import * as React from "react";
import { MathText } from "@/components/MathText";

// ─── Catalog types ────────────────────────────────────────────────────────────

type FormulaItem = {
  id: string;
  /**
   * LaTeX wrapped in \(...\) — rendered by MathText inside the button.
   * If `textLabel` is set, this field is ignored and textLabel is shown instead.
   */
  display: string;
  /** Optional plain-text label shown instead of rendered LaTeX (e.g. for delimiter buttons). */
  textLabel?: string;
  /** Raw text inserted into the textarea at the cursor position. */
  insert: string;
  /**
   * Character offset from the start of `insert` where the cursor should land.
   * For `\frac{}{}` (9 chars) cursor=6 lands inside the first pair of braces.
   * For postfix symbols like `^{\circ}` (9 chars) cursor=9 lands after all.
   */
  cursor: number;
  /** Tooltip / aria-label text. */
  title: string;
};

type FormulaGroup = {
  id: string;
  label: string;
  items: FormulaItem[];
};

// ─── Quick-access row ─────────────────────────────────────────────────────────
//
// The 14 most-used symbols shown permanently so authors don't need to
// hunt through tabs. Mirrors the flat-button style of the old Django admin.

const QUICK: FormulaItem[] = [
  { id: "q-bold",      display: "", textLabel: "B",     insert: "****",        cursor: 2,  title: "Bold  **text**" },
  { id: "q-italic",    display: "", textLabel: "I",     insert: "**",          cursor: 1,  title: "Italic  *text*" },
  { id: "q-underline", display: "", textLabel: "U",     insert: "<u></u>",     cursor: 3,  title: "Underline  <u>text</u>" },
  { id: "q-wrap",   display: "", textLabel: "\\(…\\)", insert: "\\(  \\)", cursor: 3,  title: "Wrap in inline math delimiters  \\( … \\)" },
  { id: "q-pi",     display: "", textLabel: "π",     insert: "\\pi",       cursor: 3,  title: "Pi  \\pi" },
  { id: "q-sqrt",   display: "", textLabel: "√x",    insert: "\\sqrt{}",   cursor: 6,  title: "Square root  \\sqrt{}" },
  { id: "q-sup2",   display: "", textLabel: "x²",    insert: "^{2}",       cursor: 4,  title: "Squared  ^{2}" },
  { id: "q-sup3",   display: "", textLabel: "x³",    insert: "^{3}",       cursor: 4,  title: "Cubed  ^{3}" },
  { id: "q-frac",   display: "", textLabel: "a/b",   insert: "\\frac{}{}",  cursor: 6, title: "Fraction  \\frac{}{}" },
  { id: "q-times",  display: "", textLabel: "×",     insert: "\\times ",   cursor: 7,  title: "Multiplication  \\times" },
  { id: "q-div",    display: "", textLabel: "÷",     insert: "\\div ",     cursor: 5,  title: "Division  \\div" },
  { id: "q-pm",     display: "", textLabel: "±",     insert: "\\pm ",      cursor: 4,  title: "Plus-minus  \\pm" },
  { id: "q-leq",    display: "", textLabel: "≤",     insert: "\\leq ",     cursor: 5,  title: "Less than or equal  \\leq" },
  { id: "q-geq",    display: "", textLabel: "≥",     insert: "\\geq ",     cursor: 5,  title: "Greater than or equal  \\geq" },
  { id: "q-neq",    display: "", textLabel: "≠",     insert: "\\neq ",     cursor: 5,  title: "Not equal  \\neq" },
  { id: "q-approx", display: "", textLabel: "≈",     insert: "\\approx ",  cursor: 8,  title: "Approximately  \\approx" },
  { id: "q-infty",  display: "", textLabel: "∞",     insert: "\\infty",    cursor: 6,  title: "Infinity  \\infty" },
  { id: "q-degree", display: "", textLabel: "°",     insert: "^{\\circ}",  cursor: 9,  title: "Degree  ^{\\circ}" },
];

// ─── Full formula catalog ─────────────────────────────────────────────────────

const GROUPS: FormulaGroup[] = [
  {
    id: "structure",
    label: "Structure",
    items: [
      { id: "frac",    display: "\\(\\frac{a}{b}\\)",     insert: "\\frac{}{}",     cursor: 6,  title: "Fraction  \\frac{}{}" },
      { id: "sqrt",    display: "\\(\\sqrt{x}\\)",        insert: "\\sqrt{}",       cursor: 6,  title: "Square root  \\sqrt{}" },
      { id: "nthroot", display: "\\(\\sqrt[n]{x}\\)",     insert: "\\sqrt[n]{}",    cursor: 9,  title: "Nth root  \\sqrt[n]{}" },
      { id: "sup",     display: "\\(x^{2}\\)",            insert: "^{}",            cursor: 2,  title: "Superscript  ^{}" },
      { id: "sub",     display: "\\(x_{n}\\)",            insert: "_{}",            cursor: 2,  title: "Subscript  _{}" },
      { id: "parens",  display: "\\(\\left(x\\right)\\)", insert: "\\left(\\right)",cursor: 6,  title: "Parentheses  \\left(\\right)" },
      { id: "abs",     display: "\\(\\left|x\\right|\\)", insert: "\\left|\\right|",cursor: 6,  title: "Absolute value  \\left|\\right|" },
    ],
  },
  {
    id: "algebra",
    label: "Algebra",
    items: [
      { id: "leq",    display: "\\(\\leq\\)",    insert: "\\leq ",    cursor: 5,  title: "Less than or equal  \\leq" },
      { id: "geq",    display: "\\(\\geq\\)",    insert: "\\geq ",    cursor: 5,  title: "Greater than or equal  \\geq" },
      { id: "neq",    display: "\\(\\neq\\)",    insert: "\\neq ",    cursor: 5,  title: "Not equal  \\neq" },
      { id: "pm",     display: "\\(\\pm\\)",     insert: "\\pm ",     cursor: 4,  title: "Plus-minus  \\pm" },
      { id: "times",  display: "\\(\\times\\)",  insert: "\\times ",  cursor: 7,  title: "Multiplication  \\times" },
      { id: "div",    display: "\\(\\div\\)",    insert: "\\div ",    cursor: 5,  title: "Division  \\div" },
      { id: "cdot",   display: "\\(\\cdot\\)",   insert: "\\cdot ",   cursor: 6,  title: "Dot product  \\cdot" },
      { id: "approx", display: "\\(\\approx\\)", insert: "\\approx ", cursor: 8,  title: "Approximately  \\approx" },
      { id: "infty",  display: "\\(\\infty\\)",  insert: "\\infty",   cursor: 6,  title: "Infinity  \\infty" },
    ],
  },
  {
    id: "greek",
    label: "Greek",
    items: [
      { id: "pi",      display: "\\(\\pi\\)",      insert: "\\pi",     cursor: 3,  title: "Pi  \\pi" },
      { id: "theta",   display: "\\(\\theta\\)",   insert: "\\theta",  cursor: 6,  title: "Theta  \\theta" },
      { id: "alpha",   display: "\\(\\alpha\\)",   insert: "\\alpha",  cursor: 6,  title: "Alpha  \\alpha" },
      { id: "beta",    display: "\\(\\beta\\)",    insert: "\\beta",   cursor: 5,  title: "Beta  \\beta" },
      { id: "gamma",   display: "\\(\\gamma\\)",   insert: "\\gamma",  cursor: 6,  title: "Gamma  \\gamma" },
      { id: "delta_l", display: "\\(\\delta\\)",   insert: "\\delta",  cursor: 6,  title: "delta (lower)  \\delta" },
      { id: "delta_u", display: "\\(\\Delta\\)",   insert: "\\Delta",  cursor: 6,  title: "Delta (upper)  \\Delta" },
      { id: "sigma",   display: "\\(\\sigma\\)",   insert: "\\sigma",  cursor: 6,  title: "Sigma  \\sigma" },
      { id: "lambda",  display: "\\(\\lambda\\)",  insert: "\\lambda", cursor: 7,  title: "Lambda  \\lambda" },
      { id: "mu",      display: "\\(\\mu\\)",      insert: "\\mu",     cursor: 3,  title: "Mu  \\mu" },
      { id: "omega",   display: "\\(\\omega\\)",   insert: "\\omega",  cursor: 6,  title: "Omega  \\omega" },
      { id: "phi",     display: "\\(\\phi\\)",     insert: "\\phi",    cursor: 4,  title: "Phi  \\phi" },
    ],
  },
  {
    id: "geometry",
    label: "Geometry",
    items: [
      { id: "degree",   display: "\\(90^{\\circ}\\)",      insert: "^{\\circ}",   cursor: 9,  title: "Degree (postfix)  ^{\\circ}" },
      { id: "triangle", display: "\\(\\triangle ABC\\)",   insert: "\\triangle ", cursor: 10, title: "Triangle  \\triangle" },
      { id: "angle",    display: "\\(\\angle A\\)",        insert: "\\angle ",    cursor: 7,  title: "Angle  \\angle" },
      { id: "sim",      display: "\\(\\sim\\)",            insert: "\\sim ",      cursor: 5,  title: "Similar  \\sim" },
      { id: "cong",     display: "\\(\\cong\\)",           insert: "\\cong ",     cursor: 6,  title: "Congruent  \\cong" },
      { id: "parallel", display: "\\(\\parallel\\)",       insert: "\\parallel ", cursor: 10, title: "Parallel  \\parallel" },
      { id: "perp",     display: "\\(\\perp\\)",           insert: "\\perp ",     cursor: 6,  title: "Perpendicular  \\perp" },
      { id: "overline", display: "\\(\\overline{AB}\\)",   insert: "\\overline{}", cursor: 10, title: "Overline  \\overline{}" },
      { id: "vec",      display: "\\(\\vec{v}\\)",         insert: "\\vec{}",     cursor: 5,  title: "Vector arrow  \\vec{}" },
    ],
  },
  {
    id: "functions",
    label: "Functions",
    items: [
      { id: "sin",  display: "\\(\\sin\\)",          insert: "\\sin",       cursor: 4,  title: "Sine  \\sin" },
      { id: "cos",  display: "\\(\\cos\\)",          insert: "\\cos",       cursor: 4,  title: "Cosine  \\cos" },
      { id: "tan",  display: "\\(\\tan\\)",          insert: "\\tan",       cursor: 4,  title: "Tangent  \\tan" },
      { id: "log",  display: "\\(\\log\\)",          insert: "\\log",       cursor: 4,  title: "Logarithm  \\log" },
      { id: "ln",   display: "\\(\\ln\\)",           insert: "\\ln",        cursor: 3,  title: "Natural log  \\ln" },
      { id: "lim",  display: "\\(\\lim_{}\\)",       insert: "\\lim_{}",    cursor: 6,  title: "Limit  \\lim_{}" },
      { id: "sum",  display: "\\(\\sum_{}^{}\\)",    insert: "\\sum_{}^{}", cursor: 6,  title: "Summation  \\sum_{}^{}" },
      { id: "int",  display: "\\(\\int_{}^{}\\)",    insert: "\\int_{}^{}", cursor: 6,  title: "Integral  \\int_{}^{}" },
    ],
  },
  {
    id: "sets",
    label: "Sets",
    items: [
      { id: "in",       display: "\\(\\in\\)",        insert: "\\in ",       cursor: 4,  title: "Element of  \\in" },
      { id: "notin",    display: "\\(\\notin\\)",     insert: "\\notin ",    cursor: 7,  title: "Not element  \\notin" },
      { id: "cup",      display: "\\(\\cup\\)",       insert: "\\cup ",      cursor: 5,  title: "Union  \\cup" },
      { id: "cap",      display: "\\(\\cap\\)",       insert: "\\cap ",      cursor: 5,  title: "Intersection  \\cap" },
      { id: "subset",   display: "\\(\\subset\\)",    insert: "\\subset ",   cursor: 8,  title: "Subset  \\subset" },
      { id: "subseteq", display: "\\(\\subseteq\\)",  insert: "\\subseteq ", cursor: 10, title: "Subset or equal  \\subseteq" },
      { id: "emptyset", display: "\\(\\emptyset\\)",  insert: "\\emptyset",  cursor: 9,  title: "Empty set  \\emptyset" },
      { id: "R",        display: "\\(\\mathbb{R}\\)", insert: "\\mathbb{R}", cursor: 10, title: "Real numbers  \\mathbb{R}" },
      { id: "Z",        display: "\\(\\mathbb{Z}\\)", insert: "\\mathbb{Z}", cursor: 10, title: "Integers  \\mathbb{Z}" },
    ],
  },
];

// ─── Shared button style helpers ──────────────────────────────────────────────

/** Prevent focus-steal on all formula buttons. */
function noFocusSteal(e: React.PointerEvent) {
  if (e.pointerType !== "touch") e.preventDefault();
}

const QUICK_BTN =
  "inline-flex h-8 min-w-[2.2rem] items-center justify-center rounded-lg border border-border/70 bg-card px-1.5 text-sm font-medium transition-colors hover:border-primary/50 hover:bg-primary/8 active:scale-95 active:bg-primary/12";

const GRID_BTN =
  "inline-flex h-8 min-w-[2.5rem] items-center justify-center rounded-lg border border-border/60 bg-card px-1.5 text-sm transition-colors hover:border-primary/40 hover:bg-primary/5 active:scale-95 active:bg-primary/10";

// ─── Component ────────────────────────────────────────────────────────────────

export type FormulaToolbarProps = {
  /** Called when a formula button is clicked. Parent handles insertion. */
  onInsert: (snippet: string, cursorOffset: number) => void;
};

export function FormulaToolbar({ onInsert }: FormulaToolbarProps) {
  const [activeGroupId, setActiveGroupId] = React.useState<string>(GROUPS[0].id);
  const group = GROUPS.find((g) => g.id === activeGroupId) ?? GROUPS[0];

  return (
    <div className="select-none bg-surface-2/40 px-3 py-2 space-y-2">

      {/* ── Quick-access row ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 flex-wrap">
        <span className="mr-1 shrink-0 text-[9px] font-bold uppercase tracking-widest text-muted-foreground/60">
          Quick
        </span>
        {QUICK.map((item) => (
          <button
            key={item.id}
            type="button"
            title={item.title}
            aria-label={item.title}
            onPointerDown={noFocusSteal}
            onClick={() => onInsert(item.insert, item.cursor)}
            className={QUICK_BTN}
          >
            {item.textLabel
              ? <span
                  className={[
                    "pointer-events-none leading-none",
                    item.id === "q-bold"      ? "text-sm font-black font-sans"              :
                    item.id === "q-italic"    ? "text-sm font-semibold italic font-sans"   :
                    item.id === "q-underline" ? "text-sm font-semibold underline font-sans" :
                    item.id === "q-wrap"      ? "text-[10px] font-mono"                    :
                    "text-sm",
                  ].join(" ")}
                >{item.textLabel}</span>
              : <MathText text={item.display} className="pointer-events-none leading-none" />}
          </button>
        ))}
      </div>

      {/* ── Divider ────────────────────────────────────────────────────────── */}
      <div className="border-t border-border/40" />

      {/* ── Category tab strip ─────────────────────────────────────────────── */}
      <div className="flex gap-0.5 overflow-x-auto scrollbar-none">
        {GROUPS.map((g) => (
          <button
            key={g.id}
            type="button"
            aria-pressed={g.id === activeGroupId}
            onPointerDown={noFocusSteal}
            onClick={() => setActiveGroupId(g.id)}
            className={[
              "shrink-0 rounded-md px-2 py-0.5 text-[10px] font-bold tracking-wide transition-colors",
              g.id === activeGroupId
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-surface-2",
            ].join(" ")}
          >
            {g.label}
          </button>
        ))}
      </div>

      {/* ── Formula button grid ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1">
        {group.items.map((item) => (
          <button
            key={item.id}
            type="button"
            title={item.title}
            aria-label={item.title}
            onPointerDown={noFocusSteal}
            onClick={() => onInsert(item.insert, item.cursor)}
            className={GRID_BTN}
          >
            <MathText text={item.display} className="pointer-events-none leading-none" />
          </button>
        ))}
      </div>
    </div>
  );
}

export default FormulaToolbar;
