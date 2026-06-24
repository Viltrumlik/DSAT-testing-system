# Studio Primitives — Governance Document

> **Version:** 1.0  
> **Scope:** SAT Content Studio (`questions.mastersat.uz`)  
> **Audience:** Developers adding or modifying studio authoring surfaces  

---

## What This Is

`primitives.ts` is a **canonical string-constant file** for the SAT Content Studio. It is not a component library, not a design system, and not a configuration framework. It is a single source of truth for recurring Tailwind class strings so that visual changes propagate everywhere from one edit.

---

## What Belongs Here

A token belongs in `primitives.ts` if:

1. The exact same Tailwind class string appears in **two or more unrelated files**, AND
2. A change to that class string should propagate to all of those files, AND
3. The token can be expressed as a **plain string constant** — no JSX, no props, no conditional logic

### Current Canonical Tokens

| Token | Purpose |
|---|---|
| `STUDIO_FIELD_LABEL` | Uppercase form-field label above inputs |
| `STUDIO_INPUT` | Standard text input / textarea / select |
| `STUDIO_SECTION_GAP` | Vertical spacing between page sections |
| `STUDIO_CARD` | Standard rounded bordered card container |
| `STUDIO_BTN_PRIMARY` | Single primary CTA per surface |
| `STUDIO_BTN_SECONDARY` | Auxiliary action alongside primary |
| `STUDIO_BTN_DESTRUCTIVE` | Delete/archive actions (requires confirm step) |
| `STUDIO_ERROR_BANNER` | Inline error strip for failed mutations |

---

## How to Import

```tsx
// In authoring surfaces (pages, panels, forms):
import { STUDIO_FIELD_LABEL, STUDIO_INPUT } from "@/components/studio/primitives";

// Alias for conciseness within the file (acceptable pattern):
const FIELD_LABEL = STUDIO_FIELD_LABEL;
const INPUT = STUDIO_INPUT;
```

Do **not** re-declare the string inline:
```tsx
// ✗ WRONG — starts a new drift branch
const FIELD_LABEL = "mb-1 block text-[11px] font-bold text-muted-foreground uppercase tracking-widest";

// ✓ CORRECT
import { STUDIO_FIELD_LABEL } from "@/components/studio/primitives";
const FIELD_LABEL = STUDIO_FIELD_LABEL;
```

---

## Intentional Variants — Do Not Merge

Some surfaces use **deliberately different** class strings. These are not accidents — do not "fix" them by pointing them at a canonical token.

### `BuilderSetEditorContainer` — Editor Input Variant

```ts
// This is NOT STUDIO_INPUT. It is intentional.
const INPUT = "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/30 transition-shadow";
```

**Rationale:** The center-panel editor renders on a white `bg-background` surface, not `bg-surface-2/60`. The extra `shadow-sm` and `py-2.5` give the editor form fields more visual depth to distinguish them from list-view forms. This is a design decision, not an oversight.

### `sets/new/page.tsx` — `ui-input` Token

```ts
const INPUT = "ui-input w-full rounded-xl border border-border bg-surface-2/80 px-3 py-2 text-sm shadow-sm";
```

**Rationale:** Uses the `ui-input` utility class from the global stylesheet — a different visual track intended for the set-creation form's elevated visual weight.

---

## What Does NOT Belong Here

| What | Why Not |
|---|---|
| JSX component wrappers | Use `StudioSpinner` / `StudioEmptyState` for those |
| Props-based conditional classes | That's a component, not a token |
| Theme values (colors, radii) | Those belong in `tailwind.config` / CSS variables |
| `StateTag` badge classes | Centralized in `src/components/governance/StateTag.tsx` |
| Animation keyframe classes | One-off — inline them |
| Layout classes (`flex`, `grid`) | Context-specific — not abstractable |
| Page-level spacing wrappers | Too context-dependent |

**Rule of thumb:** If you need to explain *when* to use a variant, it probably needs more than one token — which means it needs a component, not a constant.

---

## Adding a New Token

1. Confirm the class string appears verbatim in ≥2 unrelated files
2. Add the constant to `primitives.ts` with a JSDoc comment explaining its usage
3. If there's an intentional variant, document it in this file under "Intentional Variants"
4. Update all consuming files to import the token
5. Do NOT add a prop-driven variant to `primitives.ts` — if you need props, write a small component

---

## Companion Components

| Component | File | When to Use |
|---|---|---|
| `StudioSpinner` | `StudioSpinner.tsx` | Loading states in all studio list views |
| `StudioEmptyState` | `StudioEmptyState.tsx` | Zero-content states in studio lists |

These components are intentionally thin — `StudioSpinner` has one prop (`size`), `StudioEmptyState` has four. If you need more, inline it rather than adding props here.

---

## Entropy Watch

The health of this file is visible from two signals:

1. **Token count creep** — if `primitives.ts` grows beyond ~15 tokens, it is accumulating context-specific exceptions. Audit and remove.
2. **Parallel definitions** — if `grep -r "text-\[11px\] font-bold text-muted-foreground uppercase tracking-widest"` returns more than two results, drift has begun. Fix it.

Run periodically:
```bash
grep -rn "text-\[11px\] font-bold text-muted-foreground uppercase tracking-widest" src --include="*.tsx" --include="*.ts"
grep -rn "bg-surface-2/60 px-3 py-2 text-sm text-foreground" src --include="*.tsx" --include="*.ts"
```

These should return only `primitives.ts` plus its known intentional variants.
