"""
Resource-type registry for the centralized access engine.

This is the **only** module that knows about concrete resource models. It maps a
stable ``resource_type`` key (stored in ``ResourceAccessGrant.resource_type``) to:

* the Django model (resolved lazily to avoid import cycles), and
* a resolver that returns the set of **domain** subjects (``math`` / ``english``)
  the resource belongs to — normalizing the platform (``MATH`` / ``READING_WRITING``)
  vs domain vocabularies that differ across apps.

Adding a future resource type = one :func:`register` call. No schema change, no
new M2M, no new visibility filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from django.apps import apps

from .subject_mapping import platform_subject_to_domain

# Stable resource_type keys (persisted — do not rename without a data migration).
RT_PRACTICE_TEST = "practice_test"
RT_MOCK_EXAM = "mock_exam"
RT_MIDTERM = "midterm"
RT_PRACTICE_TEST_PACK = "practice_test_pack"
RT_ASSESSMENT_SET = "assessment_set"
RT_MODULE = "module"

# MockExam.kind values (string literals to avoid importing exams.models at load).
_MOCK_KIND_FULL = "MOCK_SAT"
_MOCK_KIND_MIDTERM = "MIDTERM"


@dataclass(frozen=True)
class ResourceType:
    key: str
    model_label: str  # "app_label.ModelName"
    #: instance -> iterable of domain subjects (``math``/``english``); empty if none/unknown
    domain_subjects_resolver: Callable[[object], Iterable[str]]
    #: instance -> bool (whether the resource is published/active); None => always visible-eligible
    is_published_resolver: Optional[Callable[[object], bool]] = None
    #: (queryset, frozenset[domain]) -> queryset of rows whose subject(s) are covered by
    #: those domains. Used by VisibilityService.filter_visible for subject-grant coverage.
    #: None => subject grants never widen a queryset for this type (resource grants only).
    subject_queryset_resolver: Optional[Callable[[object, frozenset], object]] = None
    #: optional ORM filter narrowing which model rows this type represents (e.g. a
    #: MockExam ``kind``). Applied to the resource-picker search queryset so two types
    #: can share one model (full ``mock_exam`` vs ``midterm``). ``None`` => all rows.
    queryset_filter: Optional[dict] = None

    def model(self):
        app_label, model_name = self.model_label.split(".")
        return apps.get_model(app_label, model_name)

    def get_instance(self, resource_id):
        return self.model().objects.filter(pk=resource_id).first()

    def domain_subjects(self, instance) -> frozenset[str]:
        if instance is None:
            return frozenset()
        return frozenset(s for s in self.domain_subjects_resolver(instance) if s)

    def is_published(self, instance) -> bool:
        if self.is_published_resolver is None or instance is None:
            return True
        return bool(self.is_published_resolver(instance))


# --- resolvers ------------------------------------------------------------

def _platform_to_domain_single(platform: object) -> list[str]:
    if not isinstance(platform, str) or not platform.strip():
        return []
    dom = platform_subject_to_domain(platform.strip())
    return [dom] if dom else []


def _practice_test_domains(pt) -> list[str]:
    return _platform_to_domain_single(getattr(pt, "subject", None))


def _module_domains(mod) -> list[str]:
    pt = getattr(mod, "practice_test", None)
    return _practice_test_domains(pt) if pt is not None else []


def _mock_exam_domains(exam) -> list[str]:
    from exams.models import MockExam

    if getattr(exam, "kind", None) == MockExam.KIND_MIDTERM:
        sub = getattr(exam, "midterm_subject", None)
        return _platform_to_domain_single(sub) if sub else []
    out: set[str] = set()
    for platform in exam.tests.values_list("subject", flat=True):
        out.update(_platform_to_domain_single(platform))
    return list(out)


def _pack_section_domains(pack) -> list[str]:
    out: set[str] = set()
    for platform in pack.sections.values_list("subject", flat=True):
        out.update(_platform_to_domain_single(platform))
    return list(out)


def _assessment_set_domains(s) -> list[str]:
    raw = getattr(s, "subject", None)
    # AssessmentSet already stores domain vocabulary (math/english).
    if isinstance(raw, str) and raw.strip().lower() in ("math", "english"):
        return [raw.strip().lower()]
    return []


# --- subject queryset resolvers (subject-grant coverage in filter_visible) ----

def _domains_to_platforms(domains: frozenset) -> list[str]:
    from .subject_mapping import domain_subject_to_platform

    return [p for p in (domain_subject_to_platform(d) for d in domains) if p]


def _practice_test_subject_qs(qs, domains):
    return qs.filter(subject__in=_domains_to_platforms(domains))


def _module_subject_qs(qs, domains):
    return qs.filter(practice_test__subject__in=_domains_to_platforms(domains))


def _mock_exam_subject_qs(qs, domains):
    # A mock is covered when every section subject is within the granted domains.
    # Approximate (safe-narrow) as: has at least one section in the domains and no
    # section outside them.
    from django.db.models import Count, Q

    platforms = _domains_to_platforms(domains)
    return (
        qs.annotate(
            _total=Count("tests", distinct=True),
            _in=Count("tests", filter=Q(tests__subject__in=platforms), distinct=True),
        )
        .filter(_total__gt=0, _total=models_F("_in"))
    )


def _pack_subject_qs(qs, domains):
    from django.db.models import Count, Q

    platforms = _domains_to_platforms(domains)
    return (
        qs.annotate(
            _total=Count("sections", distinct=True),
            _in=Count("sections", filter=Q(sections__subject__in=platforms), distinct=True),
        )
        .filter(_total__gt=0, _total=models_F("_in"))
    )


def _assessment_set_subject_qs(qs, domains):
    return qs.filter(subject__in=list(domains))


def models_F(name):
    from django.db.models import F

    return F(name)


# --- subject-scoped pack expansion -----------------------------------------
# When an admin assigns a *pack* (pastpaper / practice-test pack) they choose a
# subject scope (math / reading / both). The engine then grants access only to
# the matching section tests of that pack — not the whole pack.

#: pack resource_type -> the PracticeTest FK field pointing back at that pack
_PACK_SECTION_FIELD = {
    RT_PRACTICE_TEST_PACK: "practice_test_pack_id",
}

#: subject scope token (UI) -> platform subject stored on PracticeTest.subject
_SCOPE_TO_PLATFORM = {"math": "MATH", "reading": "READING_WRITING"}

#: resource types for which a subject scope selector is meaningful
SUBJECT_SCOPED_TYPES = frozenset(_PACK_SECTION_FIELD)


def expand_subject_targets(resource_type: str, resource_id: int, subject_scope=None):
    """
    Resolve what to actually grant for ``(resource_type, resource_id)`` under an
    optional ``subject_scope`` (``math`` / ``reading`` / ``both`` / ``None``).

    * Pack types (pastpaper / practice-test pack): returns the pack's section
      practice tests, filtered to the chosen subject (``both``/``None`` = all).
    * Any other type: returns the resource itself unchanged.
    """
    field = _PACK_SECTION_FIELD.get(resource_type)
    if field is None:
        return [(resource_type, resource_id)]

    from exams.models import PracticeTest

    qs = PracticeTest.objects.filter(**{field: resource_id})
    scope = (subject_scope or "both").strip().lower()
    if scope in _SCOPE_TO_PLATFORM:
        qs = qs.filter(subject=_SCOPE_TO_PLATFORM[scope])
    return [(RT_PRACTICE_TEST, pk) for pk in qs.values_list("id", flat=True)]


# --- registry -------------------------------------------------------------

_REGISTRY: dict[str, ResourceType] = {}


def register(rt: ResourceType) -> None:
    _REGISTRY[rt.key] = rt


def get(resource_type: str) -> Optional[ResourceType]:
    return _REGISTRY.get(resource_type)


def all_types() -> list[ResourceType]:
    return list(_REGISTRY.values())


def is_registered(resource_type: str) -> bool:
    return resource_type in _REGISTRY


def resource_label(rt: "ResourceType", instance) -> str:
    """Human-readable label for a concrete resource instance (admin console).

    Shared by the resource-picker search and the grant serializer so both render
    targets identically (e.g. ``March 2024 · MATH · INTERNATIONAL``).
    """
    if instance is None:
        return f"{getattr(rt, 'key', '?')}#?"
    title = (getattr(instance, "title", None) or getattr(instance, "name", None) or "").strip()
    if rt.key == RT_PRACTICE_TEST:
        collection = (getattr(instance, "collection_name", "") or "").strip()
        subj = getattr(instance, "subject", "")
        form = getattr(instance, "form_type", "")
        date = getattr(instance, "practice_date", "") or ""
        bits = [b for b in [collection, title, subj, form, str(date) if date else ""] if b]
        return " · ".join(bits) or f"Practice test #{instance.pk}"
    return title or f"{rt.key} #{instance.pk}"


def label_for(resource_type: str, resource_id: int) -> str:
    """Resolve ``(resource_type, resource_id)`` to a human label, or a stable fallback."""
    rt = get(resource_type)
    if rt is None or resource_id is None:
        return f"{resource_type}#{resource_id}"
    inst = rt.model().objects.filter(pk=resource_id).first()
    return resource_label(rt, inst)


register(
    ResourceType(
        RT_PRACTICE_TEST,
        "exams.PracticeTest",
        _practice_test_domains,
        subject_queryset_resolver=_practice_test_subject_qs,
    )
)
register(
    ResourceType(
        RT_MOCK_EXAM,
        "exams.MockExam",
        _mock_exam_domains,
        is_published_resolver=lambda e: bool(getattr(e, "is_published", True)),
        subject_queryset_resolver=_mock_exam_subject_qs,
        queryset_filter={"kind": _MOCK_KIND_FULL},
    )
)
register(
    ResourceType(
        RT_MIDTERM,
        "exams.MockExam",
        _mock_exam_domains,
        is_published_resolver=lambda e: bool(getattr(e, "is_published", True)),
        subject_queryset_resolver=_mock_exam_subject_qs,
        queryset_filter={"kind": _MOCK_KIND_MIDTERM},
    )
)
register(
    ResourceType(
        RT_PRACTICE_TEST_PACK,
        "exams.PracticeTestPack",
        _pack_section_domains,
        is_published_resolver=lambda p: bool(getattr(p, "is_published", True)),
        subject_queryset_resolver=_pack_subject_qs,
    )
)
register(
    ResourceType(
        RT_ASSESSMENT_SET,
        "assessments.AssessmentSet",
        _assessment_set_domains,
        is_published_resolver=lambda s: bool(getattr(s, "is_active", True)),
        subject_queryset_resolver=_assessment_set_subject_qs,
    )
)
register(
    ResourceType(
        RT_MODULE,
        "exams.Module",
        _module_domains,
        subject_queryset_resolver=_module_subject_qs,
    )
)
