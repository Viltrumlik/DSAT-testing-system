"""
Apply AI-generated rendering corrections (underline <u>, currency \\(\\$..\\))
to OpenSAT questions.

SAFETY: each field is applied ONLY if its "core" (text with all markup —
<u></u>, math delimiters, dollar signs, whitespace — removed) is UNCHANGED vs
the current stored value. This guarantees the AI only added/changed markup and
never altered wording, numbers, or order. Fields that fail the check are skipped
and reported (e.g. an agent that rewrote a sentence instead of underlining it).

Question fields go through update_bank_question (cuts a version, keeps APPROVED);
passage_text is updated in place with a refreshed content_hash. Idempotent.

Usage:
    python manage.py apply_cleanup --in /tmp/cleanup_corrections.json --dry-run
    python manage.py apply_cleanup --in /tmp/cleanup_corrections.json
"""
from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from questionbank.content_hash import compute_passage_content_hash
from questionbank.models import BankQuestion
from questionbank.services import update_bank_question

_Q_FIELDS = ("question_text", "question_prompt", "option_a", "option_b", "option_c", "option_d", "explanation")
_ALL_FIELDS = _Q_FIELDS + ("passage_text",)


def _core(s) -> str:
    s = str(s or "")
    s = s.replace("<u>", "").replace("</u>", "")
    for x in ("\\(", "\\)", "\\[", "\\]"):
        s = s.replace(x, "")
    s = s.replace("\\$", "$").replace("$", "")
    return re.sub(r"\s+", " ", s).strip()


class Command(BaseCommand):
    help = "Apply AI rendering corrections (underline/currency) with a content-preserving guard."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="infile", default="/tmp/cleanup_corrections.json")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        data = json.load(open(opts["infile"], encoding="utf-8"))

        applied_q = applied_p = skipped_drift = missing = noop = 0
        drift_samples = []

        for obj in data:
            qid = obj.get("qb_id")
            try:
                q = BankQuestion.objects.get(qb_id=qid)
            except BankQuestion.DoesNotExist:
                missing += 1
                continue

            # passage
            if "passage_text" in obj and q.passage_id:
                cur = q.passage.passage_text or ""
                new = obj["passage_text"]
                if new == cur:
                    noop += 1
                elif _core(cur) != _core(new):
                    skipped_drift += 1
                    if len(drift_samples) < 10:
                        drift_samples.append(f"{qid}/passage_text")
                elif not dry:
                    with transaction.atomic():
                        p = q.passage
                        p.passage_text = new
                        p.content_hash = compute_passage_content_hash(new)
                        p.save(update_fields=["passage_text", "content_hash", "updated_at"])
                    applied_p += 1
                else:
                    applied_p += 1

            # question fields
            updates = {}
            for f in _Q_FIELDS:
                if f not in obj:
                    continue
                cur = getattr(q, f) or ""
                new = obj[f]
                if new == cur:
                    noop += 1
                    continue
                if _core(cur) != _core(new):
                    skipped_drift += 1
                    if len(drift_samples) < 10:
                        drift_samples.append(f"{qid}/{f}")
                    continue
                updates[f] = new
            if updates:
                if not dry:
                    update_bank_question(q, **updates)
                applied_q += 1

        style = self.style.WARNING if dry else self.style.SUCCESS
        self.stdout.write(style(
            f"{'DRY-RUN — ' if dry else ''}DONE  questions updated={applied_q}  "
            f"passages updated={applied_p}  skipped(content drift)={skipped_drift}  "
            f"missing={missing}  noop={noop}"))
        if drift_samples:
            self.stdout.write("  drift-skipped: " + ", ".join(drift_samples))
