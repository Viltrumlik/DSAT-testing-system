"""
Permanent Question Bank ID allocation.

IDs look like ``QB-ENG-000001`` / ``QB-MATH-000001``. They are:
  - allocated once at creation and never change,
  - never reused (the per-subject counter is monotonic — archiving or deleting a
    question does not free its number),
  - collision-free under concurrent imports (allocation takes a row lock on the
    ``QbIdCounter`` row, mirroring the dense-order allocator already used by the
    exam engine).

This module is import-safe and side-effect free; it only touches the DB when
``allocate_qb_id`` is called inside a transaction.
"""
from __future__ import annotations

from django.db import transaction

# Subject -> short code used in the human-readable ID.
SUBJECT_ID_PREFIX = {
    "ENGLISH": "ENG",
    "MATH": "MATH",
}

# Zero-pad width for the numeric portion. 6 digits = up to 999,999 per subject;
# the format degrades gracefully (no truncation) if a subject ever exceeds it.
QB_ID_PAD_WIDTH = 6


def format_qb_id(subject: str, value: int) -> str:
    prefix = SUBJECT_ID_PREFIX[subject]
    return f"QB-{prefix}-{value:0{QB_ID_PAD_WIDTH}d}"


@transaction.atomic
def allocate_qb_id(subject: str) -> str:
    """
    Atomically allocate the next permanent qb_id for ``subject``.

    Must be called within (or it opens) a transaction; the counter row is locked
    with ``select_for_update`` so concurrent allocations serialize rather than
    collide. The counter only ever increments.
    """
    from .models import QbIdCounter

    if subject not in SUBJECT_ID_PREFIX:
        raise ValueError(f"Unknown subject for qb_id allocation: {subject!r}")

    counter, _ = QbIdCounter.objects.select_for_update().get_or_create(
        subject=subject,
        defaults={"last_value": 0},
    )
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    return format_qb_id(subject, counter.last_value)
