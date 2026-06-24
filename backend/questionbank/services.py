"""
Question Bank services — the ONLY supported way to create questions, mutate
their content, and cut immutable versions.

Why centralise here:
  - qb_id allocation, content_hash, and version snapshots must always move
    together. Scattered writes would let them drift.
  - Versions are append-only and self-sufficient (snapshot_json) so consumers
    can pin a version and stay frozen across future edits.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    BankQuestion,
    BankQuestionVersion,
    QuestionStatus,
    Subject,
)
from .qb_id import allocate_qb_id

SNAPSHOT_SCHEMA_VERSION = 1


# ──────────────────────────────────────────────────────────────────────────────
# Canonical payload — used for BOTH content_hash and the version snapshot.
# ──────────────────────────────────────────────────────────────────────────────
def _image_ref(field) -> str | None:
    """Stable string reference to an ImageField for snapshots (name, not URL)."""
    try:
        return field.name or None
    except ValueError:
        return None


def build_content_payload(q: BankQuestion) -> dict[str, Any]:
    """The graded/rendered content of a question, independent of DB identity."""
    passage_text = q.passage.passage_text if q.passage_id else ""
    return {
        "subject": q.subject,
        "question_type": q.question_type,
        "passage_text": passage_text,
        "question_text": q.question_text,
        "question_prompt": q.question_prompt,
        "options": {
            "A": q.option_a,
            "B": q.option_b,
            "C": q.option_c,
            "D": q.option_d,
        },
        "option_images": {
            "A": _image_ref(q.option_a_image),
            "B": _image_ref(q.option_b_image),
            "C": _image_ref(q.option_c_image),
            "D": _image_ref(q.option_d_image),
        },
        "question_image": _image_ref(q.question_image),
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "points": q.points,
    }


def build_snapshot(q: BankQuestion) -> dict[str, Any]:
    """Self-sufficient version snapshot: content + taxonomy + provenance."""
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "qb_id": q.qb_id,
        "status": q.status,
        "taxonomy": {
            "subject": q.subject,
            "domain": q.domain.name if q.domain_id else None,
            "domain_code": q.domain.code if q.domain_id else None,
            "skill": q.skill.name if q.skill_id else None,
            "skill_code": q.skill.code if q.skill_id else None,
            "difficulty": q.difficulty or None,
        },
        "provenance": {
            "source_type": q.source_type,
            "source_reference": q.source_reference,
            "import_batch_id": q.import_batch_id,
        },
        "content": build_content_payload(q),
    }


def _canonical_checksum(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_content_hash(q: BankQuestion) -> str:
    from .dedup import question_content_hash

    payload = build_content_payload(q)
    return question_content_hash(
        question_text=payload["question_text"],
        options=list(payload["options"].values()),
        correct_answer=payload["correct_answer"],
        passage_text=payload["passage_text"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Versioning
# ──────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def create_version(q: BankQuestion, *, user=None) -> BankQuestionVersion:
    """
    Cut a new immutable version capturing the question's current content, and
    advance ``current_version``. Append-only: previous versions are never touched.
    """
    last = (
        BankQuestionVersion.objects.select_for_update()
        .filter(bank_question=q)
        .order_by("-version_number")
        .first()
    )
    next_number = (last.version_number + 1) if last else 1
    snapshot = build_snapshot(q)
    version = BankQuestionVersion(
        bank_question=q,
        version_number=next_number,
        snapshot_json=snapshot,
        snapshot_checksum=_canonical_checksum(snapshot),
        previous_version=last,
        created_by=user,
    )
    version.save()
    # current_version pointer + refreshed content_hash on the live row.
    q.current_version = version
    q.content_hash = compute_content_hash(q)
    q.save(update_fields=["current_version", "content_hash", "updated_at"])
    return version


# ──────────────────────────────────────────────────────────────────────────────
# Creation
# ──────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def create_bank_question(
    *,
    subject: str,
    question_type: str,
    question_text: str,
    status: str = QuestionStatus.TRIAGE,
    user=None,
    cut_initial_version: bool = True,
    **fields: Any,
) -> BankQuestion:
    """
    Create a BankQuestion with an allocated permanent qb_id, compute its
    content_hash, and (by default) cut version 1.

    Taxonomy (domain/skill/difficulty) is intentionally NOT defaulted here — a
    migrated/imported question lands UNCLASSIFIED unless a human passes it.
    """
    if subject not in Subject.values:
        raise ValueError(f"Unknown subject: {subject!r}")

    # Cross-question external_id uniqueness (friendly error before the DB constraint).
    external_id = (fields.get("external_id") or "").strip()
    if external_id and BankQuestion.objects.filter(external_id=external_id).exists():
        existing = BankQuestion.objects.filter(external_id=external_id).first()
        raise ValidationError(
            f"external_id {external_id!r} already exists in the bank ({existing.qb_id})."
        )

    q = BankQuestion(
        qb_id=allocate_qb_id(subject),
        subject=subject,
        question_type=question_type,
        question_text=question_text,
        status=status,
        created_by=user,
        **fields,
    )
    q.content_hash = compute_content_hash(q)
    q.save()
    if cut_initial_version:
        create_version(q, user=user)
    return q


@transaction.atomic
def update_bank_question(q: BankQuestion, *, user=None, cut_version: bool = True, **fields: Any) -> BankQuestion:
    """
    Apply edits to a live BankQuestion, recompute content_hash, and (by default)
    cut a NEW immutable version. **Status is preserved** — editing an APPROVED
    question keeps it APPROVED (published consumers froze a copy at add-time, so
    they are unaffected). Status transitions go through triage.py, not here.
    """
    new_ext = fields.get("external_id")
    if new_ext is not None:
        new_ext = new_ext.strip()
        if new_ext and BankQuestion.objects.filter(external_id=new_ext).exclude(pk=q.pk).exists():
            existing = BankQuestion.objects.filter(external_id=new_ext).exclude(pk=q.pk).first()
            raise ValidationError(
                f"external_id {new_ext!r} already exists in the bank ({existing.qb_id})."
            )
        fields["external_id"] = new_ext

    for field, value in fields.items():
        setattr(q, field, value)
    q.content_hash = compute_content_hash(q)
    q.save()
    if cut_version:
        create_version(q, user=user)
    return q
