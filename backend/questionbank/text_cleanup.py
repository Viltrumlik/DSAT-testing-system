"""
Repair kerning-split words from PDF text extraction.

Some PDFs position characters such that the extractor inserts a space inside a
word ("repor ted" → "reported", "inver tebrate" → "invertebrate"). No geometric
threshold separates these from real spaces, so we use a DICTIONARY:

    join A + B  ⟺  A is NOT a word  AND  A+B IS a word

Joining only when the first fragment is a non-word makes this conservative — it
fixes "repor"+"ted" but leaves "and colleagues" untouched. The vendored wordlist
(web2, public domain) has base forms only, so word-membership also accepts simple
inflections (-s/-ed/-ing/-ies/-ly). With no wordlist available it is a no-op.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_WORDS_PATH = Path(__file__).parent / "data" / "words_en.txt"


@lru_cache(maxsize=1)
def _wordset() -> frozenset[str]:
    try:
        with open(_WORDS_PATH, encoding="utf-8") as fh:
            return frozenset(w.strip().lower() for w in fh if w.strip())
    except OSError:  # pragma: no cover - missing vendored asset
        return frozenset()


def _inflection_bases(t: str) -> list[str]:
    """Candidate base forms so an inflected word matches a base-form dictionary."""
    bases = [t]
    n = len(t)
    if t.endswith("ies") and n > 4:
        bases.append(t[:-3] + "y")          # studies -> study
    if t.endswith("es") and n > 3:
        bases.append(t[:-2])                # boxes -> box
    if t.endswith("s") and n > 3:
        bases.append(t[:-1])               # reports -> report
    if t.endswith("ied") and n > 4:
        bases.append(t[:-3] + "y")          # studied -> study
    if t.endswith("ed") and n > 3:
        bases.append(t[:-2])               # reported -> report
        bases.append(t[:-1])               # used -> use
    if t.endswith("ing") and n > 4:
        bases.append(t[:-3])               # reporting -> report
        bases.append(t[:-3] + "e")          # using -> use
    if t.endswith("ly") and n > 4:
        bases.append(t[:-2])               # quickly -> quick
    return bases


def _is_word(token: str) -> bool:
    ws = _wordset()
    if not ws:
        # No dictionary → treat everything as a word so the join rule never fires.
        return True
    low = token.lower()
    return any(b in ws for b in _inflection_bases(low))


def dejoin_kerning(text: str) -> str:
    """Rejoin words that PDF extraction split with a spurious space."""
    ws = _wordset()
    if not text or not ws:
        return text
    tokens = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(tokens):
        cur = tokens[i]
        if i + 1 < len(tokens):
            nxt = tokens[i + 1]
            b_core = re.sub(r"[^A-Za-z]", "", nxt)
            # cur must be a CLEAN alpha fragment; nxt must start with a letter.
            if (
                cur.isalpha()
                and len(cur) >= 2
                and b_core
                and nxt[:1].isalpha()
                and not _is_word(cur)
                and _is_word(cur + b_core)
            ):
                out.append(cur + nxt)  # keep nxt's trailing punctuation
                i += 2
                continue
        out.append(cur)
        i += 1
    return " ".join(out)
