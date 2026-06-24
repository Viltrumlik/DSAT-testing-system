"""
Bulk-import the OpenSAT question database into the Question Bank.

Source: https://github.com/Anas099X/OpenSAT  (LICENSE.md: "Users are free to use
the OpenSAT database for commercial purposes ... without restriction"). We use the
DATA only, never the code.

Data shape (per section list item):
    {
      "id": "281a4f3b",
      "domain": "Advanced Math",
      "difficulty": "Medium",
      "visuals": {"type": "null", "svg_content": "null"},
      "question": {
        "paragraph": "null" | "<passage>",
        "question": "<stem>",
        "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "correct_answer": "D",
        "explanation": "..."
      }
    }

Everything goes through questionbank.services / .triage — no raw SQL — so qb_id
allocation, content_hash, and version snapshots always move together. Re-runs are
idempotent: a question whose (subject, content_hash) already exists is skipped.

Usage:
    python manage.py import_opensat --dry-run
    python manage.py import_opensat --skill-mode provisional
    python manage.py import_opensat --sections math,english --limit 50
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from questionbank.dedup import find_duplicate, question_content_hash
from questionbank.content_hash import compute_passage_content_hash
from questionbank.latex_normalize import latexify
from questionbank.models import (
    BankDomain,
    BankPassage,
    BankQuestion,
    BankSkill,
    Difficulty,
    ImportBatch,
    QuestionStatus,
    QuestionType,
    SourceType,
    Subject,
)
from questionbank.services import create_bank_question
from questionbank.triage import approve_question, classify_question

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "opensat_snapshot.json"
DEFAULT_URL = "https://api.jsonsilo.com/public/942c3c3b-3a0c-4be3-81c2-12029def19f5"
SOURCE_REF_ROOT = "OpenSAT (github.com/Anas099X/OpenSAT)"

_SECTION_SUBJECT = {"math": Subject.MATH, "english": Subject.ENGLISH}
_NULLISH = {"", "null", "none"}
_DIFFICULTY = {"EASY": Difficulty.EASY, "MEDIUM": Difficulty.MEDIUM, "HARD": Difficulty.HARD}


def _clean(value) -> str:
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def _is_nullish(value) -> bool:
    return _clean(value).lower() in _NULLISH


class Command(BaseCommand):
    help = "Import the OpenSAT question database into the Question Bank (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT),
                            help="Path to the OpenSAT JSON snapshot.")
        parser.add_argument("--url", default="",
                            help="Fetch the JSON from this URL instead of the snapshot file.")
        parser.add_argument("--sections", default="math,english",
                            help="Comma-separated sections to import (default: math,english).")
        parser.add_argument("--skill-mode", choices=["provisional", "triage", "ai"],
                            default="provisional",
                            help="provisional: assign domain's first real skill + APPROVE (visible). "
                                 "triage: domain+difficulty only, skill null, status TRIAGE (admin-only). "
                                 "ai: not yet implemented.")
        parser.add_argument("--limit", type=int, default=0, help="Max questions per section (0 = all).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would happen without writing anything.")

    # ── data loading ──────────────────────────────────────────────────────────
    def _load(self, opts) -> dict:
        if opts["url"]:
            import urllib.request
            self.stdout.write(f"Fetching {opts['url']} …")
            with urllib.request.urlopen(opts["url"], timeout=60) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        path = Path(opts["snapshot"])
        if not path.exists():
            raise CommandError(f"Snapshot not found: {path}. Pass --url to fetch instead.")
        self.stdout.write(f"Reading {path} …")
        return json.loads(path.read_text(encoding="utf-8"))

    # ── taxonomy caches ─────────────────────────────────────────────────────────
    def _domain_for(self, subject: str, name: str, cache: dict):
        key = (subject, _clean(name).lower())
        if key not in cache:
            cache[key] = (
                BankDomain.objects.filter(subject=subject, name__iexact=_clean(name)).first()
            )
        return cache[key]

    def _first_skill_for(self, domain: BankDomain, cache: dict):
        if domain.id not in cache:
            cache[domain.id] = (
                BankSkill.objects.filter(domain=domain).order_by("display_order", "id").first()
            )
        return cache[domain.id]

    def _get_or_create_passage(self, subject, text, batch, dry_run):
        text = _clean(text)
        if not text:
            return None
        phash = compute_passage_content_hash(text)
        existing = BankPassage.objects.filter(subject=subject, content_hash=phash).first()
        if existing:
            return existing
        if dry_run:
            return None
        return BankPassage.objects.create(
            subject=subject,
            passage_text=text,
            content_hash=phash,
            source_type=SourceType.OTHER,
            source_reference=SOURCE_REF_ROOT,
            import_batch=batch,
        )

    # ── main ────────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        if opts["skill_mode"] == "ai":
            raise CommandError(
                "skill-mode 'ai' is not implemented yet. Use 'provisional' (visible now, "
                "refine skills later) or 'triage'."
            )

        data = self._load(opts)
        sections = [s.strip().lower() for s in opts["sections"].split(",") if s.strip()]
        for s in sections:
            if s not in _SECTION_SUBJECT:
                raise CommandError(f"Unknown section {s!r}. Known: {', '.join(_SECTION_SUBJECT)}.")

        dry_run = opts["dry_run"]
        skill_mode = opts["skill_mode"]
        limit = opts["limit"]

        batch = None
        if not dry_run:
            batch = ImportBatch.objects.create(
                source_type=SourceType.OTHER,
                filename="opensat_snapshot.json",
                source_reference=SOURCE_REF_ROOT,
                status=ImportBatch.Status.PARSING,
            )

        domain_cache: dict = {}
        skill_cache: dict = {}
        totals = {"created": 0, "skipped_dup": 0, "no_domain": 0, "no_skill": 0, "errors": 0}

        for section in sections:
            subject = _SECTION_SUBJECT[section]
            rows = data.get(section, []) or []
            if limit:
                rows = rows[:limit]
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n== {section} ({len(rows)} rows) → subject={subject} =="))
            sec = {"created": 0, "skipped_dup": 0, "no_domain": 0, "no_skill": 0, "errors": 0}

            for idx, row in enumerate(rows):
                try:
                    self._import_one(row, section, subject, skill_mode, batch, dry_run,
                                     domain_cache, skill_cache, sec)
                except Exception as exc:  # noqa: BLE001 — report & continue, never abort the batch
                    sec["errors"] += 1
                    rid = _clean((row or {}).get("id")) or f"#{idx}"
                    self.stderr.write(self.style.ERROR(f"  [{section}:{rid}] {exc}"))

            for k in totals:
                totals[k] += sec[k]
            self.stdout.write(
                f"  {section}: created={sec['created']} skipped_dup={sec['skipped_dup']} "
                f"no_domain={sec['no_domain']} no_skill={sec['no_skill']} errors={sec['errors']}")

        if batch is not None:
            batch.total_candidates = sum(len((data.get(s) or [])[:limit] if limit else (data.get(s) or []))
                                         for s in sections)
            batch.promoted_count = totals["created"]
            batch.status = ImportBatch.Status.PROMOTED
            batch.notes = (f"OpenSAT import: created={totals['created']} "
                           f"skipped_dup={totals['skipped_dup']} errors={totals['errors']} "
                           f"skill_mode={skill_mode}")
            batch.save()

        style = self.style.WARNING if dry_run else self.style.SUCCESS
        self.stdout.write(style(
            f"\n{'DRY-RUN — ' if dry_run else ''}DONE  created={totals['created']} "
            f"skipped_dup={totals['skipped_dup']} no_domain={totals['no_domain']} "
            f"no_skill={totals['no_skill']} errors={totals['errors']}"
            + (f"  (batch #{batch.pk})" if batch else "")))

    # ── one question ─────────────────────────────────────────────────────────────
    def _import_one(self, row, section, subject, skill_mode, batch, dry_run,
                    domain_cache, skill_cache, sec):
        q = (row or {}).get("question") or {}
        stem = latexify(_clean(q.get("question")))
        choices = q.get("choices") or {}
        opts = {k: latexify(_clean(choices.get(k))) for k in ("A", "B", "C", "D")}
        correct = _clean(q.get("correct_answer")).upper()
        explanation = latexify(_clean(q.get("explanation")))
        passage_text = "" if _is_nullish(q.get("paragraph")) else latexify(_clean(q.get("paragraph")))
        ext_id = _clean(row.get("id"))
        source_reference = f"{SOURCE_REF_ROOT} — {section}/{ext_id}" if ext_id else f"{SOURCE_REF_ROOT} — {section}"

        if not stem or not all(opts.values()) or correct not in ("A", "B", "C", "D"):
            raise ValueError("incomplete question (missing stem / choices / valid answer)")

        # difficulty
        difficulty = _DIFFICULTY.get(_clean(row.get("difficulty")).upper(), Difficulty.MEDIUM)

        # domain (required for visibility)
        domain = self._domain_for(subject, row.get("domain"), domain_cache)
        if domain is None:
            sec["no_domain"] += 1
            raise ValueError(f"no matching BankDomain for {row.get('domain')!r} "
                             f"(run seed_question_bank_taxonomy)")

        # duplicate pre-check (matches services.compute_content_hash exactly)
        chash = question_content_hash(
            question_text=stem,
            options=[opts["A"], opts["B"], opts["C"], opts["D"]],
            correct_answer=correct,
            passage_text=passage_text,
        )
        if find_duplicate(subject=subject, content_hash=chash) is not None:
            sec["skipped_dup"] += 1
            return

        # skill (required for APPROVED visibility)
        skill = None
        if skill_mode == "provisional":
            skill = self._first_skill_for(domain, skill_cache)
            if skill is None:
                sec["no_skill"] += 1
                raise ValueError(f"domain {domain.name!r} has no skills (run seed_question_bank_taxonomy)")

        if dry_run:
            sec["created"] += 1
            return

        with transaction.atomic():
            passage = self._get_or_create_passage(subject, passage_text, batch, dry_run)
            base = dict(
                subject=subject,
                question_type=QuestionType.MULTIPLE_CHOICE,
                question_text=stem,
                option_a=opts["A"], option_b=opts["B"], option_c=opts["C"], option_d=opts["D"],
                correct_answer=correct,
                explanation=explanation,
                passage=passage,
                source_type=SourceType.OTHER,
                source_reference=source_reference,
                import_batch=batch,
                points=1,
            )
            if skill_mode == "triage":
                # domain + difficulty set, skill null → TRIAGE (admin-visible, not consumable)
                obj = create_bank_question(status=QuestionStatus.TRIAGE, domain=domain,
                                           difficulty=difficulty, **base)
            else:  # provisional
                obj = create_bank_question(status=QuestionStatus.IMPORTED, **base)
                classify_question(obj, domain=domain, skill=skill, difficulty=difficulty)
                approve_question(obj)

        sec["created"] += 1
