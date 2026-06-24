from __future__ import annotations

import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from django.utils import timezone

from assessments.models import AssessmentAttempt, AssessmentHomeworkAuditEvent, HomeworkAssignment
from assessments.metrics import incr as metric_incr


class Command(BaseCommand):
    help = "Repair assessment homework integrity issues (safe, idempotent, minimal)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be changed.")
        parser.add_argument("--limit", type=int, default=2000, help="Max groups to touch.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary.")

    def handle(self, *args, **options):
        dry = bool(options["dry_run"])
        limit = int(options["limit"] or 2000)
        as_json = bool(options["json"])

        summary = defaultdict(lambda: {"count": 0, "ids": []})

        def _bump(kind: str, obj_id: int | None = None):
            summary[kind]["count"] += 1
            if obj_id is not None and len(summary[kind]["ids"]) < 50:
                summary[kind]["ids"].append(int(obj_id))

        # ── 1) De-duplicate homework per (classroom, assessment_set) ─────────
        dup_groups = (
            HomeworkAssignment.objects.values("classroom_id", "assessment_set_id")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .order_by("classroom_id", "assessment_set_id")
        )

        touched = 0
        for g in dup_groups.iterator(chunk_size=200):
            if touched >= limit:
                break

            classroom_id = g["classroom_id"]
            set_id = g["assessment_set_id"]
            group = list(
                HomeworkAssignment.objects.filter(classroom_id=classroom_id, assessment_set_id=set_id)
                .select_related("assignment")
                .order_by("-created_at", "-id")
            )
            if len(group) <= 1:
                continue

            # Prefer a canonical homework row that already has attempts.
            hw_ids = [h.pk for h in group]
            attempt_counts = {
                row["homework_id"]: row["c"]
                for row in AssessmentAttempt.objects.filter(homework_id__in=hw_ids)
                .values("homework_id")
                .annotate(c=Count("id"))
            }
            canonical = None
            for h in group:
                if attempt_counts.get(h.pk, 0) > 0:
                    canonical = h
                    break
            if canonical is None:
                canonical = group[0]

            extras = [h for h in group if h.pk != canonical.pk]

            _bump("homework.duplicate_group", canonical.pk)
            touched += 1
            if dry:
                continue

            with transaction.atomic():
                # Lock canonical and extras to avoid concurrent rewrites.
                canonical_locked = HomeworkAssignment.objects.select_for_update().get(pk=canonical.pk)

                for extra in extras:
                    extra_locked = HomeworkAssignment.objects.select_for_update().select_related("assignment").get(pk=extra.pk)

                    # Move attempts and audit events to canonical before deleting.
                    #
                    # IMPORTANT: moving attempts can violate uniq_active_attempt_per_hw_student_in_progress
                    # if a student has multiple in_progress attempts across duplicate homework rows.
                    # Strategy:
                    # - For any conflicting in_progress attempts, keep one canonical and abandon the rest.
                    moved_attempts = list(AssessmentAttempt.objects.filter(homework=extra_locked).select_for_update())
                    if moved_attempts:
                        # Resolve in-progress conflicts per student.
                        in_prog = [a for a in moved_attempts if a.status == AssessmentAttempt.STATUS_IN_PROGRESS]
                        if in_prog:
                            student_ids = {a.student_id for a in in_prog}
                            # Existing in-progress attempts on canonical homework (could exist).
                            existing = list(
                                AssessmentAttempt.objects.select_for_update()
                                .filter(homework=canonical_locked, student_id__in=student_ids, status=AssessmentAttempt.STATUS_IN_PROGRESS)
                                .order_by("-started_at", "-id")
                            )
                            existing_by_student = {}
                            for a in existing:
                                existing_by_student.setdefault(a.student_id, a)

                            # For each student, if canonical already has an in_progress attempt, abandon extras.
                            for a in in_prog:
                                if existing_by_student.get(a.student_id):
                                    a.status = AssessmentAttempt.STATUS_ABANDONED
                                    a.abandoned_at = a.abandoned_at or timezone.now()
                                    a.save(update_fields=["status", "abandoned_at"])

                        # Now move non-abandoned attempts.
                        AssessmentAttempt.objects.filter(homework=extra_locked).exclude(status=AssessmentAttempt.STATUS_ABANDONED).update(
                            homework=canonical_locked
                        )
                    AssessmentHomeworkAuditEvent.objects.filter(homework=extra_locked).update(homework=canonical_locked)

                    # Delete the linked assignment (CASCADE deletes the homework row).
                    extra_locked.assignment.delete()
                    metric_incr("integrity_repairs_applied")

        out = dict(summary)
        if as_json:
            self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
            return

        self.stdout.write("HOMEWORK INTEGRITY REPAIR")
        self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
        if dry:
            self.stdout.write("dry_run=True (no changes applied)")

