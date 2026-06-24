"""
SAT PDF question parser — PURE and PDF-library-independent.

Input is a list of per-page text strings (produced by pdf_text.extract_pages,
the only PDF-lib-dependent part). Everything here is deterministic text
processing so it can be unit-tested with synthetic pages — crucially including
the multi-page rationale merge.

Expected per-question structure (College-Board-style):

    Assessment ...
    Test: Math / Reading and Writing
    Domain: ...
    Skill: ...
    Difficulty: ...

    Question
    <stem ...>

    A. <a>
    B. <b>
    C. <c>
    D. <d>

    Correct Answer: B

    Rationale
    <explanation, MAY continue across page breaks>

MULTI-PAGE RATIONALE RULE: a Rationale runs until the NEXT record boundary
(a "Question" line or a metadata-label block) — NOT until the page ends. Page
breaks inside a rationale are stitched. Bare page numbers / running furniture are
stripped before merging so they don't contaminate the explanation.

The parser is a class so there is NO shared module state — concurrent imports are
safe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADER_LABELS = ("assessment", "test", "domain", "skill", "difficulty")
# A bare "Question" line marks the stem. Exclude "Question ID ..." — that is the
# source identifier (handled by _EXTERNAL_ID_RE), not a new question boundary.
_QUESTION_RE = re.compile(r"^\s*question\b(?!\s*id\b)", re.IGNORECASE)
_RATIONALE_RE = re.compile(r"^\s*rationale\b", re.IGNORECASE)
# A "Passage" (or "Stimulus") block introduces shared Reading & Writing passage
# text that applies to the following question(s) until the next Passage block.
_PASSAGE_RE = re.compile(r"^\s*(passage|stimulus)\b", re.IGNORECASE)
_CORRECT_RE = re.compile(r"^\s*correct\s*answer\s*[:\-]?\s*([A-D])\b", re.IGNORECASE)
# "Student Answer: A" / "Student's answer - B" — kept SEPARATE from correct.
_STUDENT_RE = re.compile(r"^\s*student'?s?\s*answer\s*[:\-]?\s*([A-D])\b", re.IGNORECASE)
# "Question ID e1a2b3c4" / "External ID: 12345" — the official source identifier.
_EXTERNAL_ID_RE = re.compile(
    r"^\s*(?:question\s*id|external\s*id)\s*[:\-]?\s*([A-Za-z0-9][\w\-]*)\s*$", re.IGNORECASE
)
_OPTION_RE = re.compile(r"^\s*([A-D])[\.\)]\s+(.*\S)\s*$")
_LABEL_RE = re.compile(r"^\s*(assessment|test|domain|skill|difficulty)\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r"^\s*(page\s+)?\d+\s*$", re.IGNORECASE)


@dataclass
class ParsedQuestion:
    subject: str = ""
    external_id: str = ""
    raw_domain: str = ""
    raw_skill: str = ""
    raw_difficulty: str = ""
    passage_text: str = ""
    question_text: str = ""
    options: dict[str, str] = field(default_factory=lambda: {"A": "", "B": "", "C": "", "D": ""})
    correct_answer: str | None = None
    student_answer: str | None = None
    explanation: str = ""
    page_start: int | None = None
    page_end: int | None = None


def _is_label_line(line: str) -> tuple[str, str] | None:
    m = _LABEL_RE.match(line)
    if not m:
        return None
    label = m.group(1).lower()
    # Guard: only treat as a label if the word is genuinely the line's label,
    # not a sentence that merely starts with e.g. "Test scores rose". Strip a
    # trailing colon so "Test:" matches "test".
    first = line.strip().lower().split()[0].rstrip(":")
    if first not in _HEADER_LABELS:
        return None
    return label, m.group(2).strip()


class _Parser:
    def __init__(self) -> None:
        self.questions: list[ParsedQuestion] = []
        self.cur: ParsedQuestion | None = None
        self.mode = "idle"  # idle | header | passage | stem | options | post_answer | rationale
        self.pending = {"subject": "", "domain": "", "skill": "", "difficulty": "", "external_id": ""}
        # Sticky passage: a "Passage" block applies to every following question
        # until the next "Passage" block — this is how Passage A → Q1..Q4 works.
        self.current_passage = ""
        self._passage_buf = ""
        # Columnar header support: some exports list bare labels (Assessment / Test /
        # Domain / Skill / Difficulty) on their own lines, then the VALUES as a
        # separate block in the same order. We collect the labels then map values
        # positionally. (Inline "Test: Math" still works via _absorb_label.)
        self._col_labels: list[str] = []
        self._col_values: list[str] = []

    # ── header accumulation ───────────────────────────────────────────────────
    def _absorb_label(self, label: str, value: str) -> None:
        if label == "test":
            low = value.lower()
            if "math" in low:
                self.pending["subject"] = "MATH"
                # Math items have no Reading & Writing passage — drop any sticky one.
                self.current_passage = ""
            elif any(w in low for w in ("reading", "writing", "english")):
                self.pending["subject"] = "ENGLISH"
        elif label in ("domain", "skill", "difficulty"):
            self.pending[label] = value

    def _finalize_passage_buffer(self) -> None:
        """Promote the accumulated passage buffer to the sticky current passage."""
        if self._passage_buf.strip():
            self.current_passage = self._passage_buf.strip()
        self._passage_buf = ""

    def _reset_pending(self) -> None:
        self.pending = {"subject": "", "domain": "", "skill": "", "difficulty": "", "external_id": ""}

    def _apply_columnar(self) -> None:
        """Map collected columnar labels → values positionally, then clear."""
        for name, val in zip(self._col_labels, self._col_values):
            self._absorb_label(name, val)
        self._col_labels = []
        self._col_values = []

    def _commit(self) -> None:
        if self.cur is not None:
            self.cur.explanation = self.cur.explanation.strip()
            self.cur.question_text = self.cur.question_text.strip()
            self.questions.append(self.cur)
            self.cur = None

    # ── main loop ─────────────────────────────────────────────────────────────
    def feed(self, page_no: int, raw: str) -> None:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            return

        # A "Passage"/"Stimulus" block starts shared passage capture. It ends a
        # rationale and any in-progress question.
        if _PASSAGE_RE.match(line):
            self._commit()
            self._passage_buf = ""
            self.current_passage = ""
            self.mode = "passage"
            return

        if _QUESTION_RE.match(line):
            if self.mode == "passage":
                self._finalize_passage_buffer()
            if self._col_labels:  # flush any in-progress columnar header
                self._apply_columnar()
            self._commit()
            self.cur = ParsedQuestion(page_start=page_no, page_end=page_no)
            if any(self.pending.values()):
                self.cur.subject = self.pending["subject"]
                self.cur.raw_domain = self.pending["domain"]
                self.cur.raw_skill = self.pending["skill"]
                self.cur.raw_difficulty = self.pending["difficulty"]
                self.cur.external_id = self.pending["external_id"]
            # Attach the sticky passage (shared by every question in its group).
            self.cur.passage_text = self.current_passage
            self._reset_pending()
            self.mode = "stem"
            return

        # "Question ID" begins a record. If a question is already open past its stem
        # (options/answer/rationale), this id starts the NEXT record → commit the
        # current one first so the id isn't mis-attached to the previous question.
        em = _EXTERNAL_ID_RE.match(line)
        if em:
            if self.cur is not None and self.mode in ("options", "post_answer", "rationale"):
                self._commit()
                self._reset_pending()
                self.mode = "header"  # leave rationale so the next header isn't eaten
            if self.cur is not None:
                self.cur.external_id = em.group(1)
            else:
                self.pending["external_id"] = em.group(1)
            return

        label = _is_label_line(line)

        # Passage capture: accumulate until a header label or a Question/Passage
        # boundary (both handled above) is reached.
        if self.mode == "passage":
            if label is not None:
                self._finalize_passage_buffer()
                self._absorb_label(*label)
                self.mode = "header"
                return
            self._passage_buf += (" " if self._passage_buf else "") + stripped
            return

        # In rationale: only a Question/Passage or a label block ends it (multi-page merge).
        if self.mode == "rationale":
            if label is not None:
                self._commit()
                self._reset_pending()
                self._absorb_label(*label)
                self.mode = "header"
                return
            self.cur.explanation += (" " if self.cur.explanation else "") + stripped
            self.cur.page_end = page_no
            return

        if label is not None and (self.cur is None or self.mode in ("idle", "header", "post_answer")):
            if self.mode == "post_answer":
                # A new record's header arrived right after an answer (no rationale).
                self._commit()
                self._reset_pending()
            lname, lval = label
            if lval:
                self._absorb_label(lname, lval)   # inline "Label: value"
            else:
                self._col_labels.append(lname)    # columnar: bare label, value follows later
            self.mode = "header"
            return

        # Columnar header values: bare labels were collected above; the following
        # plain lines are their values, in document order.
        if self._col_labels and self.cur is None and self.mode in ("header", "col_values"):
            self.mode = "col_values"
            self._col_values.append(stripped)
            if len(self._col_values) >= len(self._col_labels):
                self._apply_columnar()
                self.mode = "header"
            return

        if self.cur is None:
            return  # stray text outside any question

        # "Student Answer" is recorded SEPARATELY and never touches correct_answer.
        sm = _STUDENT_RE.match(line)
        if sm:
            self.cur.student_answer = sm.group(1).upper()
            return

        cm = _CORRECT_RE.match(line)
        if cm:
            self.cur.correct_answer = cm.group(1).upper()
            self.mode = "post_answer"
            return

        if _RATIONALE_RE.match(line):
            self.cur.explanation = ""
            self.mode = "rationale"
            return

        om = _OPTION_RE.match(line)
        if om and self.mode in ("stem", "options"):
            self.cur.options[om.group(1).upper()] = om.group(2).strip()
            self.mode = "options"
            return

        if self.mode == "stem":
            if stripped.lower() == "answer":
                return  # "Answer" is the choice-list header, not stem content
            self.cur.question_text += (" " if self.cur.question_text else "") + stripped
        elif self.mode == "options":
            last = self._last_filled_option()
            if last:
                self.cur.options[last] += " " + stripped

    def _last_filled_option(self) -> str | None:
        for letter in ("D", "C", "B", "A"):
            if self.cur and self.cur.options[letter]:
                return letter
        return None

    def finish(self) -> list[ParsedQuestion]:
        self._commit()
        return self.questions


def parse_pages(pages: list[str]) -> list[ParsedQuestion]:
    parser = _Parser()
    for idx, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            if _PAGE_NUM_RE.match(raw):
                continue  # strip bare page numbers / running furniture
            parser.feed(idx, raw)
    return parser.finish()
