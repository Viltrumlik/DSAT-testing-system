"""
Question ``order`` — **dense only** (0..n-1 per module), with ``Module`` row lock for writes.

All mutations that assign ``Question.order`` go through the same rules:
- ``select_for_update()`` on the parent ``Module`` for the duration of the reorder.
- Two-phase reassignment using a large temporary ``order`` band so ``UNIQUE(module, order)``
  is never violated while ``order`` is a ``PositiveIntegerField``.

``QuerySet.update`` / raw SQL on ``Question`` can still bypass this module — run
``exam_question_orders --repair`` or call ``dense_compact_module_orders_locked``.
"""

from __future__ import annotations

from django.apps import apps
from django.db import transaction
# Must exceed any plausible in-service dense index; used only inside locked transactions.
ORDER_TEMP_BASE = 10_000_000


def dense_compact_module_orders(module_id: int | None) -> int:
    """
    Collapse orders to contiguous ``0..n-1`` (stable by ``id``) and set
    ``Module.question_order_high_water`` to ``n-1`` (or 0 if empty).

    Does **not** acquire a module lock — callers that need concurrency safety should use
    ``dense_compact_module_orders_locked`` or hold their own ``select_for_update`` on the module.
    """
    if module_id is None:
        return 0

    QuestionModel = apps.get_model("exams", "Question")
    ModuleModel = apps.get_model("exams", "Module")

    qs = list(
        QuestionModel.objects.filter(module_id=module_id).order_by("order", "id")
    )
    batch = []
    for idx, row in enumerate(qs):
        if row.order != idx:
            row.order = idx
            batch.append(row)
    if batch:
        QuestionModel.objects.bulk_update(batch, ["order"])

    n = len(qs)
    max_ord = max(0, n - 1) if n else 0
    ModuleModel.objects.filter(pk=module_id).update(question_order_high_water=max_ord)
    return len(batch)


def dense_compact_module_orders_locked(module_id: int | None) -> int:
    """Same as ``dense_compact_module_orders`` but under ``select_for_update(Module)``."""
    if module_id is None:
        return 0
    ModuleModel = apps.get_model("exams", "Module")
    with transaction.atomic():
        ModuleModel.objects.select_for_update().get(pk=module_id)
        return dense_compact_module_orders(module_id)


def normalize_question_orders_for_module(module_id: int | None) -> int:
    return dense_compact_module_orders(module_id)


def reindex_module_questions_dense_locked(module_id: int, ordered: list) -> None:
    """
    Persist ``ordered`` sequence as ``order`` = 0..len-1.

    Caller must hold ``Module`` row lock and run inside ``transaction.atomic``.
    """
    QuestionModel = apps.get_model("exams", "Question")
    ModuleModel = apps.get_model("exams", "Module")

    n = len(ordered)
    if n == 0:
        ModuleModel.objects.filter(pk=module_id).update(question_order_high_water=0)
        return

    # Phase 1: unique temp band (PositiveIntegerField-safe).
    for i, q in enumerate(ordered):
        q.order = ORDER_TEMP_BASE + i
    with_pk = [q for q in ordered if q.pk]
    if with_pk:
        QuestionModel.objects.bulk_update(with_pk, ["order"])

    # INSERT rows that did not exist yet (full row; bypass dense hook via _plain_db_save).
    for q in ordered:
        if not q.pk:
            q.save(_plain_db_save=True)

    # Phase 2: dense indices.
    for i, q in enumerate(ordered):
        q.order = i
    QuestionModel.objects.bulk_update(ordered, ["order"])

    ModuleModel.objects.filter(pk=module_id).update(question_order_high_water=max(0, n - 1))


def save_question_dense_locked(question, *args, **kwargs) -> None:
    """
    Assign ``question`` into its module's dense order using ``question.order`` as the
    **0-based insert index** (clamped), then persist other fields with ``_plain_db_save``.

    New instances are inserted in the two-phase path (full first write); existing instances
    receive a follow-up plain save for non-order columns.
    """
    QuestionModel = apps.get_model("exams", "Question")
    ModuleModel = apps.get_model("exams", "Module")

    mid = getattr(question, "module_id", None)
    if mid is None:
        kw = dict(kwargs)
        kw["_plain_db_save"] = True
        question.save(*args, **kw)
        return

    had_pk = bool(question.pk)
    kw_plain = dict(kwargs)
    kw_plain["_plain_db_save"] = True

    with transaction.atomic():
        ModuleModel.objects.select_for_update().get(pk=mid)

        siblings = list(
            QuestionModel.objects.filter(module_id=mid)
            .exclude(pk=question.pk)
            .order_by("order", "id")
        )
        insert_at = int(getattr(question, "order", 0) or 0)
        insert_at = max(0, min(insert_at, len(siblings)))
        ordered = siblings[:insert_at] + [question] + siblings[insert_at:]

        reindex_module_questions_dense_locked(mid, ordered)

    if not had_pk:
        return

    question.save(*args, **kw_plain)


__all__ = [
    "ORDER_TEMP_BASE",
    "dense_compact_module_orders",
    "dense_compact_module_orders_locked",
    "normalize_question_orders_for_module",
    "reindex_module_questions_dense_locked",
    "save_question_dense_locked",
]
