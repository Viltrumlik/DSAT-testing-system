"""
Re-normalize LaTeX in already-imported OpenSAT questions so KaTeX/MathText renders
them (wraps bare ``\\pi``, ``x^2``, align environments in math delimiters).

Idempotent: ``latexify`` is stable, so unchanged content is skipped and re-runs are
no-ops. Question edits go through ``update_bank_question`` (recomputes content_hash,
cuts a version, preserves APPROVED status). Passages are updated in place with a
refreshed content_hash.

Usage:
    python manage.py fix_opensat_latex --dry-run
    python manage.py fix_opensat_latex
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from questionbank.content_hash import compute_passage_content_hash
from questionbank.latex_normalize import latexify
from questionbank.models import BankPassage, BankQuestion
from questionbank.services import update_bank_question

_Q_FIELDS = ("question_text", "question_prompt", "option_a", "option_b", "option_c", "option_d", "explanation")
_SOURCE_PREFIX = "OpenSAT"


class Command(BaseCommand):
    help = "Wrap bare LaTeX in imported OpenSAT questions/passages so they render (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument("--limit", type=int, default=0, help="Max questions to process (0 = all).")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        limit = opts["limit"]

        # ── passages ────────────────────────────────────────────────────────
        p_qs = BankPassage.objects.filter(source_reference__startswith=_SOURCE_PREFIX)
        p_changed = 0
        for p in p_qs.iterator():
            new = latexify(p.passage_text)
            if new == p.passage_text:
                continue
            p_changed += 1
            if not dry:
                with transaction.atomic():
                    p.passage_text = new
                    p.content_hash = compute_passage_content_hash(new)
                    p.save(update_fields=["passage_text", "content_hash", "updated_at"])
        self.stdout.write(f"passages: {p_changed} changed of {p_qs.count()}")

        # ── questions ───────────────────────────────────────────────────────
        q_qs = BankQuestion.objects.filter(source_reference__startswith=_SOURCE_PREFIX).order_by("id")
        if limit:
            q_qs = q_qs[:limit]
        total = q_qs.count()
        changed = 0
        for i, q in enumerate(q_qs.iterator(), 1):
            updates = {}
            for f in _Q_FIELDS:
                cur = getattr(q, f) or ""
                new = latexify(cur)
                if new != cur:
                    updates[f] = new
            if not updates:
                continue
            changed += 1
            if not dry:
                update_bank_question(q, **updates)
            if i % 500 == 0:
                self.stdout.write(f"  …processed {i}/{total} (changed so far: {changed})")

        style = self.style.WARNING if dry else self.style.SUCCESS
        self.stdout.write(style(
            f"{'DRY-RUN — ' if dry else ''}DONE  questions changed={changed}/{total}  "
            f"passages changed={p_changed}"))
