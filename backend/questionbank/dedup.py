"""
Single source of truth for question de-duplication.

ALL dedup paths — backfill, PDF import (against the bank), and intra-batch — go
through this module so they share one strategy and can never drift again.

DEDUP KEY: (subject, content_hash)
  - content_hash is computed over NORMALIZED content INCLUDING passage_text, so a
    stem reused under two different passages is correctly NOT a duplicate.
  - subject scopes the match (an English and a Math item that hash the same by
    coincidence are distinct questions).
  - Non-unique by design: duplicates are FLAGGED / REUSED, never DB-blocked.
"""
from __future__ import annotations

from .content_hash import compute_question_content_hash


def question_content_hash(
    *, question_text: object = "", options=None, correct_answer=None, passage_text: object = "",
) -> str:
    """The one content-hash entry point every caller must use."""
    return compute_question_content_hash(
        question_text=question_text,
        options=list(options or []),
        correct_answer=correct_answer,
        passage_text=passage_text,
    )


def find_duplicate(*, subject: str, content_hash: str):
    """Return an existing BankQuestion with the same (subject, content_hash), or None."""
    from .models import BankQuestion

    if not content_hash:
        return None
    return BankQuestion.objects.filter(subject=subject, content_hash=content_hash).first()


def find_by_external_id(external_id: str):
    """Return an existing BankQuestion carrying this official source id, or None.

    external_id collisions are EXACT duplicates (same source question), independent
    of content_hash — used by the import pipeline to flag re-imports.
    """
    from .models import BankQuestion

    external_id = (external_id or "").strip()
    if not external_id:
        return None
    return BankQuestion.objects.filter(external_id=external_id).first()
