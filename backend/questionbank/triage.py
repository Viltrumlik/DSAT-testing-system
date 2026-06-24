"""
Triage workflow — the human-driven path from imported question to APPROVED.

    IMPORTED → TRIAGE → (human classifies) → APPROVED
                                          ↘ REJECTED
    APPROVED → ARCHIVED → (restore) → APPROVED

Rules enforced here (not in views) so every caller is consistent:
  - A question cannot be APPROVED while UNCLASSIFIED (domain/skill required).
  - Classifying never auto-approves — a human still makes the approve call.
  - Approving cuts a new immutable version so the approved taxonomy is captured
    in the version history (analytics integrity).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import BankDomain, BankQuestion, BankSkill, Difficulty, QuestionStatus
from .services import create_version


class TriageError(ValidationError):
    pass


def _validate_taxonomy(question: BankQuestion, domain: BankDomain, skill: BankSkill, difficulty: str):
    if domain.subject != question.subject:
        raise TriageError(f"Domain '{domain}' is not in subject {question.subject}.")
    if skill.domain_id != domain.id:
        raise TriageError(f"Skill '{skill}' does not belong to domain '{domain}'.")
    if difficulty not in Difficulty.values:
        raise TriageError(f"Invalid difficulty: {difficulty!r}.")


@transaction.atomic
def classify_question(
    question: BankQuestion, *, domain: BankDomain, skill: BankSkill, difficulty: str, user=None,
) -> BankQuestion:
    """Assign real taxonomy. Moves IMPORTED→TRIAGE if needed. Does NOT approve."""
    _validate_taxonomy(question, domain, skill, difficulty)
    question.domain = domain
    question.skill = skill
    question.difficulty = difficulty
    if question.status == QuestionStatus.IMPORTED:
        question.status = QuestionStatus.TRIAGE
    question.save(update_fields=["domain", "skill", "difficulty", "status", "updated_at"])
    return question


@transaction.atomic
def approve_question(question: BankQuestion, *, user=None) -> BankQuestion:
    """Flip to APPROVED. Requires full taxonomy. Cuts a new version."""
    if question.domain_id is None or question.skill_id is None or not question.difficulty:
        raise TriageError("Cannot approve an UNCLASSIFIED question: domain, skill and difficulty are required.")
    question.status = QuestionStatus.APPROVED
    question.save(update_fields=["status", "updated_at"])
    create_version(question, user=user)
    return question


@transaction.atomic
def reject_question(question: BankQuestion, *, reason: str = "", user=None) -> BankQuestion:
    question.status = QuestionStatus.REJECTED
    if reason:
        meta = dict(question.metadata or {})
        meta["rejection_reason"] = reason
        question.metadata = meta
    question.save(update_fields=["status", "metadata", "updated_at"])
    return question


@transaction.atomic
def archive_question(question: BankQuestion, *, user=None) -> BankQuestion:
    question.status = QuestionStatus.ARCHIVED
    question.save(update_fields=["status", "updated_at"])
    return question


@transaction.atomic
def restore_question(question: BankQuestion, *, user=None) -> BankQuestion:
    """Restore an archived question. Returns to APPROVED if fully classified, else TRIAGE."""
    if question.domain_id and question.skill_id and question.difficulty:
        question.status = QuestionStatus.APPROVED
    else:
        question.status = QuestionStatus.TRIAGE
    question.save(update_fields=["status", "updated_at"])
    return question


@transaction.atomic
def accept_suggestion(question: BankQuestion, *, user=None) -> BankQuestion:
    """
    Human-initiated: copy the ADVISORY AI suggestion into the real taxonomy
    fields. This is the ONLY path that turns a suggestion into a classification,
    and it must be triggered by a person — suggestions never self-apply.
    """
    if not question.suggested_domain_id:
        raise TriageError("No suggestion to accept.")
    domain = question.suggested_domain
    skill = question.suggested_skill
    difficulty = question.suggested_difficulty
    if skill is None or not difficulty:
        raise TriageError("Suggestion is incomplete (needs skill + difficulty); classify manually.")
    return classify_question(question, domain=domain, skill=skill, difficulty=difficulty, user=user)
