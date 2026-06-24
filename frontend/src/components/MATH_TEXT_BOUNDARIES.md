# MathText — Rendering Boundary Governance

> **Version:** 1.0  
> **Scope:** `src/components/MathText.tsx` and its `prepareRichText` function  
> **Audience:** Developers touching any rendering surface that displays authored academic content  
> **Security classification:** Security-sensitive. Changes require explicit review.

---

## What MathText Is

`MathText` is a **narrow-purpose rendering primitive** for SAT academic content. It exists to solve one specific problem: authored text that contains LaTeX math notation and minimal emphasis must render identically for authors, in preview, and for students.

It is **not** a rich-text component. It is **not** a markdown renderer. It is **not** a publishing system.

---

## What MathText Supports — The Complete List

This list is exhaustive. If a feature is not here, it is not supported.

### 1. Academic math notation

Rendered by KaTeX via the global `renderMathInElement` CDN script loaded in `app/layout.tsx`.

| Delimiter | Type | Example |
|---|---|---|
| `\( … \)` | Inline math | `\( x^2 + 1 = 0 \)` |
| `\[ … \]` | Display math | `\[ \frac{a}{b} \]` |
| `$ … $` | Inline math (alternate) | `$x = 5$` |
| `$$ … $$` | Display math (alternate) | `$$\int_0^1 x\,dx$$` |

KaTeX supports the full SAT math notation set including fractions, roots, integrals, summations, Greek letters, and matrices.

### 2. SAT-safe emphasis

Converted from Markdown shorthand before rendering.

| Input | Output | Use for |
|---|---|---|
| `**text**` | `<b>text</b>` | Bolded terms, key words |
| `*text*` | `<i>text</i>` | Titles, emphasis |

### 3. Lightweight semantic markup — direct HTML passthrough

Authors may write these HTML tags directly in content fields. All attributes are stripped; only the bare tag is preserved.

| Tag | Use for |
|---|---|
| `<sup>` | Superscripts outside math: `x<sup>2</sup>`, `10<sup>th</sup>` |
| `<sub>` | Subscripts outside math: `H<sub>2</sub>O`, `a<sub>n</sub>` |
| `<b>` | Bold (equivalent to `**`) |
| `<i>` | Italic (equivalent to `*`) |
| `<em>` | Semantic emphasis |
| `<strong>` | Semantic strong |
| `<br>` | Line breaks within long answer text |

---

## What MathText Explicitly Does NOT Support

These are **permanent restrictions**, not temporary limitations. Do not file issues requesting them. Do not add them incrementally. If a feature below is needed, it requires a separate surface that is explicitly not a "choice text" or "question stem" field.

### Formatting forbidden in academic answer choices and question stems

| Feature | Why forbidden |
|---|---|
| Headings `# H1`, `## H2` | Not academic notation; signals structural content, not an answer |
| Lists `- item` / `1. item` | Answer choices are already a list; nested lists are never SAT content |
| Tables | Tables belong in the question stimulus, not the answer choice text |
| Arbitrary `style=""` | Style injection is a security risk; visual design is owned by Tailwind |
| `class=""` attributes | Prevents Tailwind class injection through authored content |
| Color markup | Color is reserved for UI state (correct/incorrect); not author-controlled |
| Images `<img>` | Media belongs in the stimulus block, not choice text |
| Links `<a>` | Answer choices are never navigable; all link tags are stripped |
| Video / audio embeds | Never appropriate in an answer choice |
| Generic `<div>` / `<span>` | Layout is owned by the component, not the content string |
| Arbitrary HTML | `MathText` is not a `dangerouslySetInnerHTML` passthrough |
| Extended markdown (tables, footnotes, code blocks) | Not SAT-relevant |
| `[text](url)` link syntax | Answer choices are not navigable |

---

## Security Contract

`prepareRichText` is the security boundary. It must satisfy all of:

1. **Script content removed** — `<script>…</script>` including inner text  
2. **Event handlers stripped** — `onclick`, `onload`, `onerror`, `onmouseover` on ALL tags  
3. **Attributes stripped from allowlisted tags** — `<b onclick=x>` → `<b>` (bare)  
4. **Non-allowlisted tags removed** — `<div>`, `<span>`, `<a>`, `<img>`, `<svg>`, `<form>`, `<input>`, `<iframe>`, `<object>`, `<embed>` all produce no output  
5. **Dangerous URL schemes blocked** — `javascript:`, `data:` never survive (their containing tag is removed)  
6. **HTML entities preserved as text** — `&lt;script&gt;` is inert text, not a tag  
7. **Math delimiters never corrupted** — `\( \)`, `\[ \]`, `$`, `$$` pass through unchanged

These guarantees are enforced by `src/components/__tests__/MathText.security.test.ts`. **Do not delete or weaken those tests.**

---

## When to Use MathText

Use `MathText` wherever authored academic text is **displayed** (not edited):

```tsx
// ✓ Displaying a question prompt
<MathText text={question.prompt} block className="text-base font-semibold" />

// ✓ Displaying an answer choice
<MathText text={choice.text} className="text-sm leading-relaxed" />

// ✓ Displaying explanation text
<MathText text={question.explanation} block className="text-sm text-muted-foreground" />

// ✓ Displaying stimulus/passage text
<MathText text={stimulusContext} block className="text-sm italic" />
```

---

## When NOT to Use MathText

```tsx
// ✗ Inside a textarea or input (editing surface, not display)
// ✗ For UI labels, nav items, or system messages
// ✗ For student-entered free-text (ShortTextInput is a plain textarea — correct)
// ✗ For error messages or toast notifications
// ✗ For anything that is not authored academic content
```

---

## The "One More Markdown Feature" Rule

When someone requests adding a new formatting feature to MathText, apply this filter:

1. **Is it SAT math notation?** → It probably already works via KaTeX.
2. **Is it emphasis (bold/italic/sup/sub)?** → Already supported.
3. **Is it layout, color, or structure?** → **No.** That belongs in the component layer, not content.
4. **Is it needed in answer choices or question stems?** → If not, it belongs in a purpose-specific surface, not in the shared primitive.
5. **Would adding it move MathText toward a general markdown renderer?** → **No.**

If the answer to question 5 is yes, the correct response is: add it to the specific surface that needs it without changing `MathText`.

---

## Complexity Threshold — Migrate to DOMPurify

The current sanitizer in `MathText.tsx` is intentionally simple (~15 lines). If any of the following occur, the correct response is to replace the custom regex sanitizer with `DOMPurify` (already used in `SafeHtml.tsx`):

- The sanitizer grows beyond 30 lines
- A third attack vector class requires a new regex
- An allowlisted tag needs attribute-level selective preservation (e.g., `<a href>` with safe URLs)
- A new rendering surface needs different sanitization rules

`DOMPurify` is already a dependency. Migration is a drop-in replacement of `stripDangerousTags`. Do not continue extending the regex approach beyond its current scope.

---

## Surfaces That Use MathText

| Surface | Component | Status |
|---|---|---|
| Student question stem | `StudentAttemptRunnerContainer` | ✅ MathText |
| Student MC choices | `MultipleChoiceInput` | ✅ MathText |
| Author choice live preview | `ChoiceEditor.ChoiceRow` | ✅ MathText |
| Author preview pane (prompt) | `SATQuestionPreview` | ⚠️ Container renderMath (math only; see below) |
| Author preview pane (choices) | `SATQuestionPreview` | ⚠️ Container renderMath (math only; see below) |
| Author preview pane (explanation) | `SATQuestionPreview` | ⚠️ Container renderMath (math only; see below) |
| Review page | `SafeHtml` via DOMPurify + KaTeX | ⚠️ Different pipeline (see below) |
| Bank page list | `QuestionCard` | ℹ️ Intentional: truncated index view |
| Module panel list | `ModuleQuestionsPanel` | ℹ️ Intentional: truncated list view |

### ⚠️ SATQuestionPreview — Known partial gap

`SATQuestionPreview` uses a `ref` on the whole container and calls `renderMath` once. This renders **math correctly** but does **not render `**bold**` or `*italic*` markdown** because `{c.text}` is a React text node. Phase 2 of the preview fidelity roadmap (see `PREVIEW_FIDELITY.md`) replaces these text nodes with `MathText`.

### ⚠️ Review page (`SafeHtml`) — Known divergence

The review page uses `SafeHtml` (DOMPurify + MathJax/KaTeX retry) — a different pipeline. For standard SAT math this is largely equivalent. The divergence is tracked in `PREVIEW_FIDELITY.md`. Until convergence, avoid LaTeX features that differ between KaTeX 0.16 and MathJax 3.

---

## How to Update This Document

1. When a new formatting feature is added to `MathText` → add it to the "Supports" table
2. When a new rendering surface adopts `MathText` → update the surfaces table
3. When the complexity threshold is hit and DOMPurify is adopted → replace the "Security Contract" section
4. When `SATQuestionPreview` is migrated to `MathText` → mark that row ✅

The person making the change is responsible for updating this document.
