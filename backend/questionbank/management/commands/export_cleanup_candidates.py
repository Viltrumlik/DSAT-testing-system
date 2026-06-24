"""
Export OpenSAT questions that need AI cleanup (missing <u> underline, broken
currency dollars) to a JSON file for offline correction.

Selection:
  - ENGLISH questions whose stem references an "underlined" portion (need <u>).
  - MATH questions with a "naked" unescaped ``$`` (currency that the frontend
    mis-pairs as a math delimiter) — flagged when the naked-$ count is odd
    (guaranteed stray) or currency keywords are present.

Usage: python manage.py export_cleanup_candidates --out /tmp/cleanup_candidates.json
"""
from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand

from questionbank.models import BankQuestion

_SRC = "OpenSAT"
_CURRENCY_KW = re.compile(r'\b(cost|price|fee|per |paid|dollar|rent|charge|sells?|buy|spend|discount|salary|wage)\b', re.I)
# strip escaped \$ and delimited spans, then any remaining $ is "naked"
_DELIM = re.compile(r'\$\$.*?\$\$|\\\(.*?\\\)|\\\[.*?\\\]', re.DOTALL)


def naked_dollar_count(text: str) -> int:
    if not text:
        return 0
    t = text.replace('\\$', '')          # escaped dollars are literal, not delimiters
    t = _DELIM.sub('', t)                 # remove already-delimited math
    return t.count('$')


class Command(BaseCommand):
    help = "Export questions needing AI cleanup (underline / currency) to JSON."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="/tmp/cleanup_candidates.json")

    def handle(self, *args, **opts):
        base = BankQuestion.objects.filter(source_reference__startswith=_SRC)
        out = []
        n_underline = n_currency = 0

        for q in base.iterator():
            reasons = []
            if q.subject == "ENGLISH" and re.search(r'underlin', q.question_text or '', re.I):
                reasons.append("underline")
                n_underline += 1
            # currency only meaningful where naked $ exists
            fields_text = " ".join([
                q.question_text or "", q.option_a or "", q.option_b or "",
                q.option_c or "", q.option_d or "", q.explanation or "",
                (q.passage.passage_text if q.passage_id else ""),
            ])
            naked = naked_dollar_count(fields_text)
            if naked and (naked % 2 == 1 or _CURRENCY_KW.search(fields_text)):
                reasons.append("currency")
                n_currency += 1
            if not reasons:
                continue
            out.append({
                "qb_id": q.qb_id,
                "subject": q.subject,
                "reasons": reasons,
                "passage_text": q.passage.passage_text if q.passage_id else "",
                "question_text": q.question_text or "",
                "option_a": q.option_a or "", "option_b": q.option_b or "",
                "option_c": q.option_c or "", "option_d": q.option_d or "",
                "correct_answer": q.correct_answer,
                "explanation": q.explanation or "",
            })

        with open(opts["out"], "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(
            f"exported {len(out)} candidates → {opts['out']}  "
            f"(underline={n_underline}, currency={n_currency})"))
