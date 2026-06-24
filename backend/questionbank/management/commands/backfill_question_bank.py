"""
M1 backfill: copy existing exam + assessment questions into the Question Bank.

Guarantees:
  - IDEMPOTENT: a consumer row already linked (bank_question set) is skipped.
  - NON-DESTRUCTIVE: only creates bank rows and sets the nullable link FK on the
    consumer row. No existing content is modified or deleted.
  - NO FABRICATED METADATA: everything lands status=TRIAGE with NULL domain/skill.
    The assessment set's category (reliable, human-authored) is captured as an
    ADVISORY suggestion only — never auto-applied.
  - DEDUP: questions with an identical content_hash reuse the existing bank row
    instead of creating a duplicate.

Usage:
    python manage.py backfill_question_bank --dry-run        # report only
    python manage.py backfill_question_bank --source=exams
    python manage.py backfill_question_bank                  # both sources, commit
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from questionbank.dedup import find_duplicate, question_content_hash


class _Abort(Exception):
    """Raised to roll back the outer transaction in --dry-run mode."""


# Map assessment category "Domain › Subdomain" → (domain, skill) advisory match.
def _match_taxonomy(subject, category):
    from questionbank.models import BankDomain, BankSkill
    if not category:
        return None, None
    parts = [p.strip() for p in category.replace("›", "›").split("›")]
    domain_name = parts[0] if parts else ""
    skill_name = parts[1] if len(parts) > 1 else ""
    domain = BankDomain.objects.filter(subject=subject, name__iexact=domain_name).first()
    skill = None
    if domain and skill_name:
        skill = BankSkill.objects.filter(domain=domain, name__iexact=skill_name).first()
    return domain, skill


class Command(BaseCommand):
    help = "Backfill existing exam/assessment questions into the Question Bank (M1)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report counts, commit nothing.")
        parser.add_argument(
            "--source", choices=["exams", "assessments", "both"], default="both",
            help="Which consumer to backfill from.",
        )
        parser.add_argument("--limit", type=int, default=0, help="Max rows per source (0 = all).")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        source = opts["source"]
        limit = opts["limit"]
        stats = {"created": 0, "deduped": 0, "skipped_linked": 0, "errors": 0}

        try:
            with transaction.atomic():
                if source in ("exams", "both"):
                    self._backfill_exams(stats, limit)
                if source in ("assessments", "both"):
                    self._backfill_assessments(stats, limit)
                if dry:
                    raise _Abort()
        except _Abort:
            self.stdout.write(self.style.WARNING("DRY RUN — rolled back, nothing committed."))

        self.stdout.write(self.style.SUCCESS(
            "Backfill {}: created={created}, deduped={deduped}, "
            "skipped(already linked)={skipped_linked}, errors={errors}".format(
                "(dry-run)" if dry else "committed", **stats
            )
        ))

    # ── exams.Question ────────────────────────────────────────────────────────
    def _backfill_exams(self, stats, limit):
        from exams.models import Question
        from questionbank.models import QuestionType, Subject

        qs = Question.objects.filter(bank_question__isnull=True).order_by("id")
        if limit:
            qs = qs[:limit]

        for q in qs.iterator():
            try:
                subject = Subject.MATH if q.question_type == "MATH" else Subject.ENGLISH
                qtype = QuestionType.STUDENT_PRODUCED if q.is_math_input else QuestionType.MULTIPLE_CHOICE
                if q.is_math_input:
                    correct = [v.strip() for v in (q.correct_answers or "").split(",") if v.strip()]
                else:
                    correct = (q.correct_answers or "").strip().upper() or None
                fields = dict(
                    question_prompt=q.question_prompt or "",
                    option_a=q.option_a or "", option_b=q.option_b or "",
                    option_c=q.option_c or "", option_d=q.option_d or "",
                    correct_answer=correct,
                    explanation=q.explanation or "",
                    points=q.score or 1,
                    source_reference=f"exams.Question:{q.id}",
                )
                bank = self._get_or_create_bank(
                    subject=subject, question_type=qtype,
                    question_text=q.question_text or "",
                    source_type="MIGRATED_EXAM", fields=fields, stats=stats,
                )
                self._copy_images_exam(q, bank)
                q.bank_question = bank
                q.bank_version = bank.current_version
                q.save(update_fields=["bank_question", "bank_version"], _plain_db_save=True)
            except Exception as exc:  # noqa: BLE001 — keep going, count failures
                stats["errors"] += 1
                self.stderr.write(f"exams.Question {q.id}: {exc}")

    def _copy_images_exam(self, q, bank):
        # Reference the same uploaded file names; no file copy needed (shared MEDIA).
        changed = []
        for src, dst in (
            ("question_image", "question_image"), ("option_a_image", "option_a_image"),
            ("option_b_image", "option_b_image"), ("option_c_image", "option_c_image"),
            ("option_d_image", "option_d_image"),
        ):
            f = getattr(q, src)
            if f and f.name:
                setattr(bank, dst, f.name)
                changed.append(dst)
        if changed:
            bank.save(update_fields=changed)

    # ── assessments.AssessmentQuestion ────────────────────────────────────────
    def _backfill_assessments(self, stats, limit):
        from assessments.models import AssessmentQuestion
        from questionbank.models import QuestionType, Subject

        type_map = {
            "multiple_choice": QuestionType.MULTIPLE_CHOICE,
            "short_text": QuestionType.SHORT_TEXT,
            "numeric": QuestionType.NUMERIC,
            "boolean": QuestionType.BOOLEAN,
        }
        qs = (
            AssessmentQuestion.objects.filter(bank_question__isnull=True)
            .select_related("assessment_set").order_by("id")
        )
        if limit:
            qs = qs[:limit]

        for q in qs.iterator():
            try:
                aset = q.assessment_set
                subject = Subject.MATH if aset.subject == "math" else Subject.ENGLISH
                qtype = type_map.get(q.question_type, QuestionType.MULTIPLE_CHOICE)
                opts = {"A": "", "B": "", "C": "", "D": ""}
                for choice in (q.choices or []):
                    cid = str(choice.get("id", "")).strip().upper()
                    if cid in opts:
                        opts[cid] = choice.get("text", "") or ""
                fields = dict(
                    question_prompt=q.question_prompt or "",
                    option_a=opts["A"], option_b=opts["B"], option_c=opts["C"], option_d=opts["D"],
                    correct_answer=q.correct_answer,
                    explanation=q.explanation or "",
                    points=q.points or 1,
                    source_reference=f"assessments.AssessmentQuestion:{q.id}",
                )
                bank = self._get_or_create_bank(
                    subject=subject, question_type=qtype,
                    question_text=q.prompt or "",
                    source_type="MIGRATED_ASSESSMENT", fields=fields, stats=stats,
                )
                # Advisory taxonomy suggestion from the set category — NEVER auto-applied.
                self._attach_category_suggestion(bank, subject, aset.category)
                self._copy_images_assessment(q, bank)
                q.bank_question = bank
                q.bank_version = bank.current_version
                q.save(update_fields=["bank_question", "bank_version"])
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
                self.stderr.write(f"assessments.AssessmentQuestion {q.id}: {exc}")

    def _attach_category_suggestion(self, bank, subject, category):
        if not category or bank.suggestion_model:
            return
        domain, skill = _match_taxonomy(subject, category)
        if not domain:
            return
        bank.suggested_domain = domain
        bank.suggested_skill = skill
        bank.suggestion_model = "migration:assessment_category"
        bank.suggestion_rationale = f"Migrated from assessment set category '{category}'."
        bank.save(update_fields=["suggested_domain", "suggested_skill", "suggestion_model", "suggestion_rationale"])

    def _copy_images_assessment(self, q, bank):
        changed = []
        for src, dst in (
            ("question_image", "question_image"), ("option_a_image", "option_a_image"),
            ("option_b_image", "option_b_image"), ("option_c_image", "option_c_image"),
            ("option_d_image", "option_d_image"),
        ):
            f = getattr(q, src)
            if f and f.name:
                setattr(bank, dst, f.name)
                changed.append(dst)
        if changed:
            bank.save(update_fields=changed)

    # ── shared create-or-dedup ────────────────────────────────────────────────
    def _get_or_create_bank(self, *, subject, question_type, question_text, source_type, fields, stats):
        from questionbank.services import create_bank_question

        # Backfilled exam/assessment questions carry their stimulus inline (no
        # separate passage row), so passage_text is "" here — same unified hash
        # + (subject, content_hash) dedup strategy as the PDF import path.
        chash = question_content_hash(
            question_text=question_text,
            options=[fields["option_a"], fields["option_b"], fields["option_c"], fields["option_d"]],
            correct_answer=fields["correct_answer"],
            passage_text="",
        )
        existing = find_duplicate(subject=subject, content_hash=chash)
        if existing:
            stats["deduped"] += 1
            return existing
        bank = create_bank_question(
            subject=subject, question_type=question_type, question_text=question_text,
            source_type=source_type, **fields,
        )
        stats["created"] += 1
        return bank
