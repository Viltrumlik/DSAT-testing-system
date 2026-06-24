"""
Import pipeline orchestration: pages → candidates → (human review) → promotion.

    create_batch_from_pages(pages)   parse + validate + stage ImportCandidates
    promote_batch(batch)             approved-by-human candidates → BankQuestions

Promotion lands questions in TRIAGE (never auto-classified), dedups by
content_hash, reuses BankPassage for shared passages, and records provenance
(source_type / source_reference / import_batch). Nothing is auto-approved.
"""
from __future__ import annotations

from django.db import transaction

from .content_hash import compute_passage_content_hash
from .dedup import find_by_external_id, find_duplicate
from .import_validation import candidate_content_hash, validate_parsed
from .models import (
    BankPassage,
    BankQuestion,
    ImportBatch,
    ImportCandidate,
    QuestionStatus,
    SourceType,
    Subject,
)
from .pdf_parser import ParsedQuestion, parse_pages
from .services import create_bank_question
from .text_cleanup import dejoin_kerning


def _clean_parsed(q: ParsedQuestion) -> None:
    """Repair kerning-split words in the parsed text fields (in place)."""
    q.question_text = dejoin_kerning(q.question_text)
    q.passage_text = dejoin_kerning(q.passage_text)
    q.explanation = dejoin_kerning(q.explanation)
    for letter in ("A", "B", "C", "D"):
        q.options[letter] = dejoin_kerning(q.options[letter])


@transaction.atomic
def create_batch_from_pages(
    pages: list[str], *, filename: str = "", source_reference: str = "", uploaded_by=None,
) -> ImportBatch:
    batch = ImportBatch.objects.create(
        source_type=SourceType.PDF_IMPORT,
        filename=filename,
        source_reference=source_reference,
        uploaded_by=uploaded_by,
        status=ImportBatch.Status.READY,
    )
    parsed = parse_pages(pages)
    for q in parsed:
        _clean_parsed(q)
    seen_in_batch: dict[tuple[str, str], int] = {}  # (subject, hash) -> earlier candidate order
    seen_ext: dict[str, int] = {}  # external_id -> earlier candidate order
    for order, q in enumerate(parsed):
        status, messages = validate_parsed(q)
        chash = candidate_content_hash(q)
        subject = q.subject if q.subject in Subject.values else Subject.ENGLISH
        ext = (q.external_id or "").strip()

        # Exact-only dedup: external_id collision OR (subject, content_hash) against
        # the bank, then intra-batch by external_id and by hash.
        dup = find_by_external_id(ext) or find_duplicate(subject=subject, content_hash=chash)
        if dup is not None:
            status = ImportCandidate.Validation.DUPLICATE
            messages = [f"Duplicate of existing bank question {dup.qb_id}."] + messages
        elif ext and ext in seen_ext:
            status = ImportCandidate.Validation.DUPLICATE
            messages = [f"Duplicate external_id of candidate #{seen_ext[ext]} in this batch."] + messages
        elif (subject, chash) in seen_in_batch:
            status = ImportCandidate.Validation.DUPLICATE
            messages = [
                f"Duplicate of candidate #{seen_in_batch[(subject, chash)]} in this batch."
            ] + messages
        else:
            seen_in_batch[(subject, chash)] = order
            if ext:
                seen_ext[ext] = order

        ImportCandidate.objects.create(
            batch=batch, order=order,
            subject=q.subject or "",
            external_id=ext,
            raw_domain=q.raw_domain, raw_skill=q.raw_skill, raw_difficulty=q.raw_difficulty,
            passage_text=q.passage_text,
            question_text=q.question_text,
            option_a=q.options["A"], option_b=q.options["B"],
            option_c=q.options["C"], option_d=q.options["D"],
            correct_answer=q.correct_answer, student_answer=q.student_answer,
            explanation=q.explanation,
            content_hash=chash, page_start=q.page_start, page_end=q.page_end,
            validation_status=status, validation_messages=messages, duplicate_of=dup,
        )
    batch.total_candidates = len(parsed)
    batch.save(update_fields=["total_candidates"])
    return batch


def _exclude_figure_candidates(batch: ImportBatch, images_by_page: dict) -> int:
    """IMPORT POLICY: a question on a page that contains a figure (embedded raster
    OR vector-drawn chart) is EXCLUDED — figures are author-only, not auto-imported.
    Marks such candidates ERROR with a clear reason. Returns the count excluded."""
    if not images_by_page:
        return 0
    fig_pages = set(images_by_page)
    excluded = 0
    for cand in batch.candidates.all():
        start = cand.page_start or 0
        end = cand.page_end or start
        if any(p in fig_pages for p in range(start, end + 1)):
            if cand.validation_status != ImportCandidate.Validation.ERROR:
                cand.validation_status = ImportCandidate.Validation.ERROR
                cand.validation_messages = [
                    "Excluded: question contains a figure/chart — add it manually in the bank."
                ] + list(cand.validation_messages or [])
                cand.save(update_fields=["validation_status", "validation_messages"])
                excluded += 1
    return excluded


def create_batch_from_pdf(
    pdf_path: str, *, filename: str = "", source_reference: str = "", uploaded_by=None,
) -> ImportBatch:
    """End-to-end PDF ingestion: text → candidates (English text-only policy enforced
    in validate_parsed), then exclude any candidate on a page that has a figure
    (PyMuPDF detection). Degrades to text-only when PyMuPDF is unavailable."""
    from .pdf_text import extract_page_images, extract_pages

    pages = extract_pages(pdf_path)
    batch = create_batch_from_pages(
        pages, filename=filename, source_reference=source_reference, uploaded_by=uploaded_by,
    )
    _exclude_figure_candidates(batch, extract_page_images(pdf_path))
    return batch


def _get_or_create_passage(candidate: ImportCandidate, subject: str) -> BankPassage | None:
    """
    Reuse an existing BankPassage with identical text (no duplication) or create
    one. Returns None when the candidate has no passage (e.g. math items).
    """
    text = (candidate.passage_text or "").strip()
    if not text:
        return None
    phash = compute_passage_content_hash(text)
    existing = BankPassage.objects.filter(subject=subject, content_hash=phash).first()
    if existing is not None:
        return existing
    return BankPassage.objects.create(
        subject=subject,
        passage_text=candidate.passage_text,
        content_hash=phash,
        source_type=SourceType.PDF_IMPORT,
        source_reference=candidate.batch.source_reference or candidate.batch.filename,
        import_batch=candidate.batch,
    )


def _candidate_subject(c: ImportCandidate) -> str:
    return c.subject if c.subject in Subject.values else Subject.ENGLISH


@transaction.atomic
def promote_candidate(candidate: ImportCandidate, *, user=None) -> BankQuestion:
    """Promote one reviewed candidate into the bank (TRIAGE). Idempotent."""
    if candidate.promoted_question_id:
        return candidate.promoted_question
    if candidate.duplicate_of_id:
        candidate.promoted_question = candidate.duplicate_of
        candidate.save(update_fields=["promoted_question"])
        return candidate.duplicate_of

    subject = _candidate_subject(candidate)
    # Reuse/create the shared passage so Q1..Qn under one passage point at a
    # single BankPassage row (no passage-text duplication).
    passage = _get_or_create_passage(candidate, subject)
    # PDF candidates are multiple-choice; SPR/other types are authored manually.
    fields = dict(
        passage=passage,
        external_id=candidate.external_id,
        option_a=candidate.option_a, option_b=candidate.option_b,
        option_c=candidate.option_c, option_d=candidate.option_d,
        correct_answer=candidate.correct_answer,
        student_answer=candidate.student_answer,
        explanation=candidate.explanation,
        source_type=SourceType.PDF_IMPORT,
        source_reference=candidate.batch.source_reference or candidate.batch.filename,
        import_batch=candidate.batch,
    )
    # Best-effort page-level diagram carried from the PDF (see extract_page_images).
    if candidate.question_image:
        fields["question_image"] = candidate.question_image
    bank = create_bank_question(
        subject=subject, question_type="MULTIPLE_CHOICE",
        question_text=candidate.question_text, status=QuestionStatus.TRIAGE,
        user=user, **fields,
    )
    candidate.promoted_question = bank
    candidate.save(update_fields=["promoted_question"])
    return bank


@transaction.atomic
def promote_batch(batch: ImportBatch, *, include_warnings: bool = True, user=None) -> int:
    """
    Promote all non-error, non-duplicate candidates in a batch. Returns the count
    of newly promoted questions. ERROR candidates are skipped (must be fixed in
    review first); DUPLICATE candidates link to the existing bank row.
    """
    allowed = [ImportCandidate.Validation.VALID]
    if include_warnings:
        allowed.append(ImportCandidate.Validation.WARNING)

    promoted = 0
    for cand in batch.candidates.filter(validation_status__in=allowed, promoted_question__isnull=True):
        promote_candidate(cand, user=user)
        promoted += 1
    batch.promoted_count = (batch.promoted_count or 0) + promoted
    batch.status = ImportBatch.Status.PROMOTED
    batch.save(update_fields=["promoted_count", "status"])
    return promoted
