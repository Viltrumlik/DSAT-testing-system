from __future__ import annotations

import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, F

from assessments.models import AssessmentAttempt, AssessmentHomeworkAuditEvent, HomeworkAssignment


class Command(BaseCommand):
    help = "Read-only integrity audit for assessment homework assignments (prints counts + sample IDs)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Max IDs to print per category.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")

    def handle(self, *args, **options):
        limit = int(options["limit"] or 50)
        as_json = bool(options["json"])

        report: dict[str, dict] = {}

        # Duplicate homework per (classroom, assessment_set) (should be unique).
        dup_groups = (
            HomeworkAssignment.objects.values("classroom_id", "assessment_set_id")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .order_by("-c", "classroom_id", "assessment_set_id")
        )
        dup_rows = []
        for g in dup_groups[:limit]:
            ids = list(
                HomeworkAssignment.objects.filter(
                    classroom_id=g["classroom_id"],
                    assessment_set_id=g["assessment_set_id"],
                )
                .order_by("-created_at", "-id")
                .values_list("id", flat=True)[: min(25, limit)]
            )
            dup_rows.append(
                {
                    "classroom_id": g["classroom_id"],
                    "assessment_set_id": g["assessment_set_id"],
                    "count": g["c"],
                    "homework_ids": ids,
                }
            )

        report["homework"] = {
            "duplicate_homework_per_classroom_set": {"count": dup_groups.count(), "rows": dup_rows},
        }

        # Homework whose linked Assignment points at a different classroom (should never happen).
        classroom_mismatch_qs = HomeworkAssignment.objects.exclude(assignment__classroom_id=F("classroom_id"))
        classroom_mismatch = list(classroom_mismatch_qs.values_list("id", flat=True)[:limit])
        report["homework"]["homework_assignment_classroom_mismatch"] = {
            "count": classroom_mismatch_qs.count(),
            "ids": classroom_mismatch,
        }

        # Attempt integrity for duplicate homework groups is repaired during de-dupe.
        report["attempts"] = {"note": "Attempt audit is handled by repair_homework_integrity when de-duping."}

        # Audit event counts by type (helps spot abnormal volumes).
        by_type = defaultdict(int)
        for row in AssessmentHomeworkAuditEvent.objects.values("event_type").annotate(c=Count("id")).order_by("-c"):
            by_type[str(row["event_type"])] = int(row["c"])
        report["audit_events"] = {"counts_by_event_type": dict(by_type)}

        if as_json:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write("HOMEWORK INTEGRITY AUDIT")
        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))

