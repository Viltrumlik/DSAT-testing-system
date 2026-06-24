"""
Normalize "bare" LaTeX / structural markup in imported content so the frontend
KaTeX/MathText pipeline renders it.

The platform convention is LaTeX wrapped in math delimiters (``\\( … \\)`` inline,
``\\[ … \\]`` display). Imported sources (e.g. OpenSAT) embed:
  - LaTeX commands/exponents WITHOUT delimiters (``\\pi``, ``x^2``)  → wrap them
  - escaped dollars / currency (``\\$40``)                          → render-safe ``\\(\\$\\)``
  - MATH environments (align*, cases, array, …) without delimiters  → wrap in ``\\[ \\]``
  - TEXT environments (center, quote, …) — KaTeX can't render these → strip to inner text
  - ``tabular`` tables — KaTeX can't render these                  → flatten to a text grid
  - Asymptote figure code ``[asy] … [/asy]`` — not renderable      → strip

Guarantees (verified over the OpenSAT snapshot):
  - Idempotent: ``latexify(latexify(x)) == latexify(x)``.
  - Never unbalances ``\\(``/``\\)``.
  - Only wraps tokens carrying a math signal (``\\cmd``, ``^``, ``_``), never plain words.
"""
from __future__ import annotations

import re

# KaTeX-renderable math environments → display math.
_MATH_ENVS = {
    "align", "align*", "aligned", "alignedat", "cases", "array", "matrix",
    "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "gather",
    "gather*", "gathered", "equation", "equation*", "split", "multline", "eqnarray",
}
# Text layout environments KaTeX cannot render → keep only the inner text.
_TEXT_ENVS = {
    "center", "flushleft", "flushright", "quote", "quotation", "verse",
    "verbatim", "document", "figure", "table", "minipage",
}

_ASY = re.compile(r'\[asy\].*?\[/asy\]', re.DOTALL)
_ENV = re.compile(r'\\begin\{([a-zA-Z*]+)\}(.*?)\\end\{[a-zA-Z*]+\}', re.DOTALL)
# A \[ … \] that we previously wrapped around an environment (so re-runs can re-decide).
_ENV_UNWRAP = re.compile(r'\\\[\s*(\\begin\{[a-zA-Z*]+\}.*?\\end\{[a-zA-Z*]+\})\s*\\\]', re.DOTALL)

_PROTECT = re.compile(r'\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]|\\\$', re.DOTALL)
_CMD = r'\\(?!begin\b|end\b)[a-zA-Z]+(?:\{[^{}]*\}|\[[^\[\]]*\])*'
_POW = r'(?:\([^()]+\)|\[[^\[\]]+\]|[A-Za-z0-9]+)(?:[\^_](?:\{[^{}]*\}|[A-Za-z0-9]+))+'
_TOKEN = re.compile(_CMD + '|' + _POW)


def _tabular_to_text(block: str) -> str:
    """Flatten a LaTeX tabular into a plain ' | '-separated text grid (KaTeX can't
    render tabular; MathText turns the newlines into <br>)."""
    inner = re.sub(r'\\begin\{tabular\}\{[^}]*\}', '', block)
    inner = re.sub(r'\\end\{tabular\}', '', inner)
    inner = inner.replace('\\hline', '\n')
    lines = []
    for row in re.split(r'\\\\', inner):
        for sub in row.split('\n'):
            cells = [c.strip() for c in sub.split('&') if c.strip()]
            if cells:
                lines.append(' | '.join(cells))
    return '\n'.join(lines)


def _handle_structures(text: str) -> str:
    text = _ASY.sub('', text)
    text = _ENV_UNWRAP.sub(r'\1', text)  # undo prior wrapping so we re-classify

    def repl(m):
        env = m.group(1)
        if env == 'tabular':
            return _tabular_to_text(m.group(0))
        if env in _TEXT_ENVS:
            return m.group(2).strip()
        return '\\[' + m.group(0) + '\\]'  # math env (known or unknown) → display

    return _ENV.sub(repl, text)


def _wrap_segment(seg: str) -> str:
    return _TOKEN.sub(lambda m: '\\(' + m.group(0) + '\\)', seg)


def latexify(text: str | None) -> str:
    """Return ``text`` with bare LaTeX/structures normalized for rendering. Safe on None/plain."""
    if not text:
        return text or ""
    if not re.search(r'[\\^_$]', text) and '[asy]' not in text:
        return text

    text = _handle_structures(text)

    out: list[str] = []
    last = 0
    for m in _PROTECT.finditer(text):
        out.append(_wrap_segment(text[last:m.start()]))
        span = m.group(0)
        # A lone escaped dollar (`\$`, literal currency) renders broken because the
        # frontend math splitter pairs the raw `$`. Wrap as `\(\$\)` so KaTeX emits a
        # literal `$` and no stray `$` can form a false delimiter pair.
        out.append('\\(\\$\\)' if span == '\\$' else span)
        last = m.end()
    out.append(_wrap_segment(text[last:]))
    return ''.join(out)
