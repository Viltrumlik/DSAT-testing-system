"""Detect and repair inconsistent ``Question.order`` values per module (gaps are normal under sparse mode)."""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db.models import Count

from .question_ordering import dense_compact_module_orders


def question_duplicate_order_counts() -> dict[tuple[int, int], int]:
    """Maps (module_id, order_value) → count where count > 1 violates UNIQUE(module_id, order)."""
    QuestionModel = apps.get_model("exams", "Question")
    rows = (
        QuestionModel.objects.exclude(module_id__isnull=True)
        .values("module_id", "order")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    return {(int(row["module_id"]), int(row["order"])): int(row["c"]) for row in rows}


def audit_question_orders(*, module_ids: list[int] | None = None) -> dict[str, Any]:
    """
    Duplicate (module_id, order) keys are actionable; sparse gaps between consecutive orders are reported
    separately (acceptable unless you intend dense numbering).
    """
    QuestionModel = apps.get_model("exams", "Question")

    dup_index = question_duplicate_order_counts()
    if module_ids:
        dup_filtered = {(m, o): c for ((m, o), c) in dup_index.items() if m in set(module_ids)}
    else:
        dup_filtered = dict(dup_index)

    dup_list = [
        {"module_id": m, "order": o, "count": c}
        for ((m, o), c) in sorted(dup_filtered.items(), key=lambda x: (x[0][0], x[0][1]))
    ]

    qs = QuestionModel.objects.exclude(module_id__isnull=True).values_list("module_id", flat=True).distinct()
    if module_ids:
        qs = qs.filter(module_id__in=module_ids)
    mids = sorted(set(qs))

    gap_stats: dict[int, dict[str, Any]] = {}
    for mid in mids:
        orders = list(
            QuestionModel.objects.filter(module_id=mid)
            .order_by("order", "id")
            .values_list("order", flat=True)
        )
        if len(orders) <= 1:
            continue
        gap_segments = sum(1 for i in range(len(orders) - 1) if orders[i + 1] > orders[i] + 1)
        dup_local = len(orders) != len(set(orders))
        if gap_segments or dup_local:
            gap_stats[int(mid)] = {
                "questions": len(orders),
                "duplicate_orders": dup_local,
                "sparse_gap_segments": gap_segments,
            }

    return {
        "duplicate_pairs": dup_list,
        "modules_with_duplicate_orders": sorted({m for (m, _o) in dup_filtered}),
        "gap_stats": gap_stats,
    }


def repair_question_orders_for_module(module_id: int) -> int:
    """Dense-reindex module questions (use after duplicates or when dense ordering is required)."""
    return dense_compact_module_orders(module_id)


def repair_modules_with_duplicate_orders(*, limit: int | None = None) -> list[int]:
    """Fix every module that still has duplicate (module_id, order) keys."""
    affected = sorted({m for (m, _o) in question_duplicate_order_counts().keys()})
    if limit is not None:
        affected = affected[: int(limit)]

    repaired: list[int] = []
    for mid in affected:
        repair_question_orders_for_module(mid)
        repaired.append(mid)
    return repaired


def module_has_duplicate_orders(module_id: int) -> bool:
    """Cheap existence check for duplicate (module_id, order) pairs."""
    QuestionModel = apps.get_model("exams", "Question")
    from django.db.models import Count

    return (
        QuestionModel.objects.filter(module_id=module_id)
        .values("order")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .exists()
    )


__all__ = [
    "audit_question_orders",
    "module_has_duplicate_orders",
    "question_duplicate_order_counts",
    "repair_modules_with_duplicate_orders",
    "repair_question_orders_for_module",
]
