import katex from "katex";

type RenderOptions = {
  root?: HTMLElement | null;
};

/**
 * Delimiter definitions — ordered longest-first so $$ is matched before $.
 */
const DELIMITERS = [
  { left: "$$", right: "$$", display: true },
  { left: "\\[", right: "\\]", display: true },
  { left: "\\(", right: "\\)", display: false },
  { left: "$", right: "$", display: false },
];

/**
 * Escape a string for use in a RegExp character class.
 */
function escRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Build a single regex that matches any delimiter pair.
 * Captures: (delimIndex ignored — use group structure), raw LaTeX body.
 * We build alternation in order so $$ wins over $.
 */
function buildPattern(): RegExp {
  const parts = DELIMITERS.map(({ left, right }) => {
    const l = escRe(left);
    const r = escRe(right);
    // Use [\\s\\S] (double-escaped) to allow multi-line math — non-greedy.
    // NOTE: template literals strip lone backslashes in unrecognised escape
    // sequences (e.g. \s → s) when bundlers minify. Use \\ to get a literal
    // backslash in the compiled string so the character class is [\s\S].
    return "(?:" + l + ")([\\s\\S]*?)(?:" + r + ")";
  });
  return new RegExp(parts.join("|"), "g");
}

const MATH_PATTERN = buildPattern();

/**
 * Convert a raw string containing LaTeX delimiters into HTML by calling
 * katex.renderToString() on each match. Returns the HTML string.
 *
 * This function does NOT touch the DOM — it works on strings only.
 * Pair it with dangerouslySetInnerHTML or an innerHTML assignment.
 */
export function renderMathInString(text: string): string {
  // Reset lastIndex so the regex is reusable
  MATH_PATTERN.lastIndex = 0;

  let result = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = MATH_PATTERN.exec(text)) !== null) {
    // Append literal text before this match
    result += text.slice(lastIndex, match.index);

    // Find which delimiter group matched by checking which capture group
    // is defined. Each delimiter contributes exactly one capture group.
    let latex = "";
    let display = false;
    for (let i = 0; i < DELIMITERS.length; i++) {
      const captured = match[i + 1];
      if (captured !== undefined) {
        latex = captured;
        display = DELIMITERS[i].display;
        break;
      }
    }

    try {
      result += katex.renderToString(latex, {
        displayMode: display,
        throwOnError: false,
        trust: false,
        strict: false,
        output: "html",
      });
    } catch {
      // Never crash — fall back to original text
      result += match[0];
    }

    lastIndex = match.index + match[0].length;
  }

  // Append any trailing literal text
  result += text.slice(lastIndex);

  return result;
}

/**
 * renderMath — walk all text nodes inside `root` and render any LaTeX
 * delimiters found using katex.renderToString().
 *
 * - SSR-safe (no-op server-side)
 * - Uses only katex core (no auto-render extension needed)
 * - Works with dangerouslySetInnerHTML content because it operates on
 *   already-parsed DOM text nodes, not raw HTML strings
 */
export function renderMath(options?: RenderOptions) {
  if (typeof window === "undefined") return;

  const root = options?.root ?? document.body;
  if (!root) return;

  try {
    processNode(root);
  } catch {
    // Rendering must never crash the runner.
  }
}

/**
 * Tags whose text content must NOT be processed (they contain code or
 * are already rendered math output).
 */
const SKIP_TAGS = new Set([
  "script",
  "style",
  "textarea",
  "pre",
  "code",
  "annotation",
  "annotation-xml",
]);

function processNode(node: Node): void {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent ?? "";
    // Quick bail: if no delimiter character present, skip
    if (!text.includes("\\") && !text.includes("$")) return;

    // Check if this text node actually matches a delimiter
    MATH_PATTERN.lastIndex = 0;
    if (!MATH_PATTERN.test(text)) return;

    // Replace this text node with the rendered HTML
    const rendered = renderMathInString(text);
    const wrapper = document.createElement("span");
    wrapper.innerHTML = rendered;
    node.parentNode?.replaceChild(wrapper, node);
    return;
  }

  if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as Element;
    const tag = el.tagName.toLowerCase();

    // Skip already-rendered KaTeX nodes and disallowed tags
    if (
      SKIP_TAGS.has(tag) ||
      el.classList.contains("katex") ||
      el.classList.contains("katex-display")
    ) {
      return;
    }

    // Process children (collect first to avoid mutation during iteration)
    const children = Array.from(node.childNodes);
    for (const child of children) {
      processNode(child);
    }
  }
}
