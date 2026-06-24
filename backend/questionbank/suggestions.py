"""
AI-assisted triage suggestions — ADVISORY ONLY.

A suggestion writes the ``suggested_*`` fields on a BankQuestion. It NEVER writes
the real ``domain``/``skill``/``difficulty`` fields and NEVER changes status. A
human must explicitly accept it (questionbank.triage.accept_suggestion).

Providers are pluggable so the heavy/external model call (Claude) is swappable
and test-friendly. The default provider is a deterministic heuristic with low
confidence — good enough to pre-sort a triage queue, never authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

from .models import BankDomain, BankQuestion, BankSkill, Difficulty


@dataclass
class Suggestion:
    domain: BankDomain | None
    skill: BankSkill | None
    difficulty: str
    confidence: float
    model: str
    rationale: str


class SuggestionProvider:
    """Interface. Implementations return a Suggestion for a question."""

    name = "base"

    def suggest(self, question: BankQuestion) -> Suggestion:  # pragma: no cover - interface
        raise NotImplementedError


class HeuristicSuggestionProvider(SuggestionProvider):
    """Keyword-overlap heuristic against skill names. Deterministic, offline."""

    name = "heuristic-v1"

    def suggest(self, question: BankQuestion) -> Suggestion:
        text = " ".join(
            filter(None, [question.question_text, question.question_prompt, question.explanation])
        ).lower()
        best_skill = None
        best_score = 0
        for skill in BankSkill.objects.filter(domain__subject=question.subject).select_related("domain"):
            tokens = {t for t in skill.name.lower().replace(",", " ").split() if len(t) > 3}
            score = sum(1 for t in tokens if t in text)
            if score > best_score:
                best_score, best_skill = score, skill
        if best_skill and best_score > 0:
            confidence = min(0.5, 0.15 * best_score)  # capped low — advisory only
            return Suggestion(
                domain=best_skill.domain, skill=best_skill, difficulty="",
                confidence=confidence, model=self.name,
                rationale=f"Keyword overlap ({best_score}) with skill '{best_skill.name}'.",
            )
        return Suggestion(
            domain=None, skill=None, difficulty="", confidence=0.0, model=self.name,
            rationale="No confident keyword match; manual classification needed.",
        )


class ClaudeSuggestionProvider(SuggestionProvider):
    """
    Claude-backed classifier. Wired but inert unless QUESTION_BANK_ANTHROPIC_KEY
    is configured — falls back to the heuristic provider otherwise so nothing
    breaks in environments without the key. Implementation of the live call is
    intentionally deferred to M3 wiring; the seam exists now.
    """

    name = "claude"

    def suggest(self, question: BankQuestion) -> Suggestion:  # pragma: no cover - external
        key = getattr(settings, "QUESTION_BANK_ANTHROPIC_KEY", "")
        if not key:
            return HeuristicSuggestionProvider().suggest(question)
        raise NotImplementedError(
            "Live Claude classification is wired in M3 (PDF import). "
            "Set QUESTION_BANK_ANTHROPIC_KEY and implement the API call here."
        )


def get_provider() -> SuggestionProvider:
    path = getattr(
        settings, "QUESTION_BANK_SUGGESTION_PROVIDER",
        "questionbank.suggestions.HeuristicSuggestionProvider",
    )
    return import_string(path)()


def generate_suggestion(question: BankQuestion, *, provider: SuggestionProvider | None = None) -> BankQuestion:
    """Compute and STORE an advisory suggestion. Does not classify or approve."""
    provider = provider or get_provider()
    s = provider.suggest(question)
    if s.difficulty and s.difficulty not in Difficulty.values:
        s.difficulty = ""
    question.suggested_domain = s.domain
    question.suggested_skill = s.skill
    question.suggested_difficulty = s.difficulty
    question.suggestion_confidence = s.confidence
    question.suggestion_model = s.model
    question.suggestion_rationale = s.rationale
    question.save(update_fields=[
        "suggested_domain", "suggested_skill", "suggested_difficulty",
        "suggestion_confidence", "suggestion_model", "suggestion_rationale", "updated_at",
    ])
    return question
