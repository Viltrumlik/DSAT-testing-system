"""
Management command: check_snapshot_integrity

Scans all AssessmentSetVersion rows and recomputes the SHA-256 checksum of
each snapshot_json, comparing against the stored snapshot_checksum. Reports
any rows where the checksum doesn't match (possible DB corruption or direct
SQL mutation).

Usage:
    python manage.py check_snapshot_integrity
    python manage.py check_snapshot_integrity --set-id 42
    python manage.py check_snapshot_integrity --fail-fast
    python manage.py check_snapshot_integrity --quiet      # only print failures

Exit code:
    0  — all checksums pass
    1  — one or more checksum mismatches found
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from assessments.domain.snapshot_builder import verify_snapshot_integrity
from assessments.models import AssessmentSetVersion


class Command(BaseCommand):
    help = "Verify SHA-256 integrity of all stored assessment snapshot records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--set-id",
            type=int,
            default=None,
            help="Only check versions for this AssessmentSet ID.",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            default=False,
            help="Stop after the first integrity failure.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Only print failed rows (suppress OK progress).",
        )

    def handle(self, *args, **options):
        set_id = options["set_id"]
        fail_fast = options["fail_fast"]
        quiet = options["quiet"]

        qs = AssessmentSetVersion.objects.all().order_by("assessment_set_id", "version_number")
        if set_id is not None:
            qs = qs.filter(assessment_set_id=set_id)

        total = qs.count()
        if not quiet:
            self.stdout.write(f"Checking {total} snapshot(s)…")

        checked = 0
        failures = 0

        for version in qs.iterator(chunk_size=200):
            checked += 1
            ok = verify_snapshot_integrity(version.snapshot_json, version.snapshot_checksum)

            if ok:
                if not quiet:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK   set={version.assessment_set_id} v{version.version_number} "
                            f"({version.snapshot_checksum[:12]}…)"
                        )
                    )
            else:
                failures += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  FAIL set={version.assessment_set_id} v{version.version_number} "
                        f"id={version.pk} — stored checksum {version.snapshot_checksum[:12]}… "
                        f"does not match recomputed checksum"
                    )
                )
                if fail_fast:
                    raise CommandError(
                        f"Integrity failure on AssessmentSetVersion #{version.pk} — aborting."
                    )

        self.stdout.write("")
        if failures == 0:
            self.stdout.write(self.style.SUCCESS(f"All {checked} snapshot(s) passed integrity check."))
        else:
            self.stderr.write(
                self.style.ERROR(
                    f"{failures}/{checked} snapshot(s) FAILED integrity check. "
                    "Investigate immediately — these are immutable academic records."
                )
            )
            raise SystemExit(1)
