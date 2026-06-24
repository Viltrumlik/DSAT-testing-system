"""
Canonical content-hash computation for Question Bank duplicate detection.

A SINGLE normalization routine is used everywhere — import, validation, batch
cleanup, and future dedup workflows — so that two records hash identically iff
their normalized content is identical. The hash is intentionally NOT enforced as
a unique constraint: legitimate near-duplicates exist (e.g. the same stem with a
different correct option), so collisions are *flagged for review*, never blocked.

Normalization rules (stable contract — changing these changes every hash, so
bump CONTENT_HASH_VERSION and plan a recompute if you ever do):
  - Unicode NFKC normalize.
  - Lowercase.
  - Strip, then collapse all internal whitespace runs to a single space.
  - Join fields with a record separator so field boundaries cannot be smeared
    (e.g. moving a word from the stem into option A must change the hash).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterable

CONTENT_HASH_VERSION = 1

# Record separator (ASCII 30) — cannot appear in normalized text, so it is a safe
# field delimiter that prevents content from one field bleeding into another.
_FIELD_SEP = "\x1e"
_WS_RE = re.compile(r"\s+")


def normalize_text(value: object) -> str:
    """Normalize a single text fragment for hashing/comparison."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.lower().strip()
    s = _WS_RE.sub(" ", s)
    return s


def _normalize_correct_answer(correct_answer: object) -> str:
    """
    Correct answers may be a string, number, bool, or list of acceptable values.
    Order-insensitive for lists (``["2/3", "0.667"]`` == ``["0.667", "2/3"]``).
    """
    if isinstance(correct_answer, (list, tuple)):
        parts = sorted(normalize_text(p) for p in correct_answer)
        return ",".join(parts)
    return normalize_text(correct_answer)


def compute_question_content_hash(
    *,
    question_text: object = "",
    options: Iterable[object] | None = None,
    correct_answer: object = None,
    passage_text: object = "",
) -> str:
    """
    Deterministic SHA-256 over normalized question content.

    ``options`` is the ordered A–D choice texts (empty strings allowed). Passage
    text is included so that two questions sharing a stem but attached to
    different passages do not collide.
    """
    opt_list = list(options or [])
    fields = [
        normalize_text(passage_text),
        normalize_text(question_text),
        _FIELD_SEP.join(normalize_text(o) for o in opt_list),
        _normalize_correct_answer(correct_answer),
    ]
    canonical = _FIELD_SEP.join(fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_passage_content_hash(passage_text: object) -> str:
    """Deterministic SHA-256 over normalized passage text alone."""
    canonical = normalize_text(passage_text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
