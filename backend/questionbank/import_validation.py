"""
Validation for parsed import candidates. Pure functions over a ParsedQuestion.

Produces (status, messages). Mirrors the SAT integrity rules used elsewhere:
missing stem/choices/answer, answer-not-in-choices, malformed choices, empty or
truncation-suspected rationale, and duplicate detection by content_hash.
"""
from __future__ import annotations

from .dedup import question_content_hash
from .models import ImportCandidate
from .pdf_parser import ParsedQuestion

_STATUS = ImportCandidate.Validation


def _looks_truncated(text: str) -> bool:
    """Rationale that ends mid-sentence (no terminal punctuation) is suspect —
    typically a page-boundary cut that failed to merge."""
    t = (text or "").strip()
    if not t:
        return False
    return t[-1] not in ".!?\"')]"


def validate_parsed(q: ParsedQuestion) -> tuple[str, list[str]]:
    messages: list[str] = []
    status = _STATUS.VALID

    # IMPORT POLICY: PDF import is English + text-only. Math and unknown-subject
    # questions are EXCLUDED (not promotable) — author those manually in the bank.
    # (Figure-bearing questions are excluded separately in create_batch_from_pdf,
    # which is the only place that can see the PDF's embedded/vector graphics.)
    if q.subject == "MATH":
        return _STATUS.ERROR, ["Excluded: Math import is disabled — add Math questions manually."]
    if q.subject != "ENGLISH":
        return _STATUS.ERROR, [
            "Excluded: subject is not English — only English text-only questions are imported."
        ]

    is_spr = q.correct_answer is None and not any(q.options.values())

    if not q.question_text.strip():
        messages.append("Missing question text.")
        status = _STATUS.ERROR

    filled = [k for k, v in q.options.items() if v.strip()]
    if not is_spr:
        if len(filled) < 2:
            messages.append("Fewer than two answer choices.")
            status = _STATUS.ERROR
        if not q.correct_answer:
            messages.append("Missing correct answer.")
            status = _STATUS.ERROR
        elif q.correct_answer not in filled:
            messages.append(f"Correct answer '{q.correct_answer}' is not among the filled choices.")
            status = _STATUS.ERROR

    if not q.explanation.strip():
        messages.append("Missing rationale/explanation.")
        if status != _STATUS.ERROR:
            status = _STATUS.WARNING
    elif _looks_truncated(q.explanation):
        messages.append("Rationale may be truncated at a page boundary (ends mid-sentence).")
        if status != _STATUS.ERROR:
            status = _STATUS.WARNING

    return status, messages


def candidate_content_hash(q: ParsedQuestion) -> str:
    return question_content_hash(
        question_text=q.question_text,
        options=[q.options["A"], q.options["B"], q.options["C"], q.options["D"]],
        correct_answer=q.correct_answer,
        passage_text=q.passage_text,
    )
