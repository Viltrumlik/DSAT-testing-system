"""
Management command: backfill_snapshot_versions

For all HomeworkAssignment rows where set_version_id IS NULL, find the
most appropriate published AssessmentSetVersion and pin it.

SELECTION STRATEGY:
  For each HomeworkAssignment with set_version_id=NULL:
    1. Find all published versions for the set.
    2. Select the version whose published_at is closest to (but not after)
       the assignment's created_at. This is the version that was current
       when the teacher made the assignment.
    3. If no version was published before the assignment was created
       (set was assigned before its first publish), skip — leave NULL.
    4. If published_at is available and matches, use it.
       Else fall back to the latest version.

  After backfilling HomeworkAssignment rows, also backfill AssessmentAttempt
  rows that are NULL but whose homework now has a version.

SAFETY:
  - --dry-run: report what WOULD be changed without writing anything.
  - --set-id: restrict to a single AssessmentSet.
  - --attempt-only: only backfill AssessmentAttempt rows (not HomeworkAssignment).
  - All changes happen inside per-row transactions for crash safety.
  - Governance events are emitted for every pinned row.
  - Already-pinned rows (set_version_id IS NOT NULL) are never touched.

ROLLBACK SAFETY:
  set_version is nullable; setting it to a value is additive. Rolling back
  this command means setting it back to NULL — that is safe (falls back to
  live-lookup compatibility path).

EXIT CODES:
  0 — completed (possibly with 0 rows updated)
  1 — unrecoverable error

Usage:
    python manage.py backfill_snapshot_versions
    python manage.py backfill_snapshot_versions --dry-run
    python manage.py backfill_snapshot_versions --set-id 42
    python manage.py backfill_snapshot_versions --set-id 42 --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill set_version FK on HomeworkAssignment and AssessmentAttempt rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be changed without making any writes.",
        )
        parser.add_argument(
            "--set-id",
            type=int,
            default=None,
            help="Restrict to HomeworkAssignments for this AssessmentSet PK.",
        )
        parser.add_argument(
            "--attempt-only",
            action="store_true",
            default=False,
            help="Only backfill AssessmentAttempt rows; skip HomeworkAssignment.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress per-row output; only print summary.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        set_id = options["set_id"]
        attempt_only = options["attempt_only"]
        quiet = options["quiet"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no writes will be made."))

        hw_pinned = hw_skipped = hw_error = 0
        att_pinned = att_skipped = att_error = 0

        # ── Phase 1: HomeworkAssignment ───────────────────────────────────────
        if not attempt_only:
            hw_pinned, hw_skipped, hw_error = self._backfill_homework(
                dry_run=dry_run, set_id=set_id, quiet=quiet
            )

        # ── Phase 2: AssessmentAttempt ────────────────────────────────────────
        att_pinned, att_skipped, att_error = self._backfill_attempts(
            dry_run=dry_run, set_id=set_id, quiet=quiet
        )

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("─── Summary ───────────────────────────────────"))
        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            f"{prefix}HomeworkAssignment: {hw_pinned} pinned, "
            f"{hw_skipped} skipped (no eligible version), {hw_error} errors"
        )
        self.stdout.write(
            f"{prefix}AssessmentAttempt:  {att_pinned} pinned, "
            f"{att_skipped} skipped, {att_error} errors"
        )

        if hw_error or att_error:
            self.stderr.write(self.style.ERROR("Completed with errors. Review output above."))
            raise SystemExit(1)

    def _find_best_version(self, aset, created_at):
        """
        Select the version whose published_at is nearest to created_at.
        Returns None if no eligible version exists.
        """
        from assessments.models import AssessmentSetVersion

        # Best: the most recent version published at or before created_at.
        version = (
            AssessmentSetVersion.objects.filter(
                assessment_set=aset,
                published_at__lte=created_at,
            )
            .order_by("-published_at", "-version_number")
            .first()
        )
        if version:
            return version

        # Fallback: if no version was published before created_at (set was
        # assigned before first publish), use the earliest version.
        # This handles the case where publish happened retroactively.
        return (
            AssessmentSetVersion.objects.filter(assessment_set=aset)
            .order_by("version_number")
            .first()
        )

    def _backfill_homework(self, *, dry_run: bool, set_id, quiet: bool):
        from assessments.models import HomeworkAssignment, GovernanceEvent
        from assessments.domain.governance_events import emit_governance_event

        qs = HomeworkAssignment.objects.filter(
            set_version_id__isnull=True
        ).select_related("assessment_set").order_by("id")

        if set_id is not None:
            qs = qs.filter(assessment_set_id=set_id)

        pinned = skipped = errors = 0

        for hw in qs.iterator(chunk_size=200):
            try:
                version = self._find_best_version(hw.assessment_set, hw.created_at)

                if version is None:
                    if not quiet:
                        self.stdout.write(
                            f"  SKIP  HomeworkAssignment #{hw.pk}: "
                            f"set #{hw.assessment_set_id} has no published versions."
                        )
                    skipped += 1
                    continue

                if not quiet:
                    prefix = "[DRY RUN] " if dry_run else ""
                    self.stdout.write(
                        f"  {prefix}PIN   HomeworkAssignment #{hw.pk} → "
                        f"AssessmentSetVersion #{version.pk} (v{version.version_number})"
                    )

                if not dry_run:
                    with transaction.atomic():
                        HomeworkAssignment.objects.filter(pk=hw.pk, set_version_id__isnull=True).update(
                            set_version=version
                        )
                        emit_governance_event(
                            event_type=GovernanceEvent.EVENT_ASSIGNMENT_PIN,
                            actor=None,  # system backfill
                            entity_type="HomeworkAssignment",
                            entity_id=hw.pk,
                            payload={
                                "set_id": hw.assessment_set_id,
                                "pinned_version_id": version.pk,
                                "pinned_version_number": version.version_number,
                                "source": "backfill_snapshot_versions",
                                "snapshot_pinned": True,
                            },
                        )
                pinned += 1

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"  ERROR HomeworkAssignment #{hw.pk}: {exc}"
                    )
                )
                errors += 1

        return pinned, skipped, errors

    def _backfill_attempts(self, *, dry_run: bool, set_id, quiet: bool):
        from assessments.models import AssessmentAttempt, GovernanceEvent
        from assessments.domain.governance_events import emit_governance_event

        qs = (
            AssessmentAttempt.objects.filter(set_version_id__isnull=True)
            .select_related("homework__assessment_set", "homework__set_version")
            .order_by("id")
        )

        if set_id is not None:
            qs = qs.filter(homework__assessment_set_id=set_id)

        pinned = skipped = errors = 0

        for att in qs.iterator(chunk_size=200):
            try:
                hw = att.homework
                # If homework has a pinned version, inherit it.
                if hw.set_version_id:
                    version = hw.set_version
                else:
                    # Homework also has no version — try to find best by started_at.
                    version = self._find_best_version(
                        hw.assessment_set, att.started_at or att.last_activity_at
                    )

                if version is None:
                    if not quiet:
                        self.stdout.write(
                            f"  SKIP  AssessmentAttempt #{att.pk}: no eligible version."
                        )
                    skipped += 1
                    continue

                if not quiet:
                    prefix = "[DRY RUN] " if dry_run else ""
                    self.stdout.write(
                        f"  {prefix}PIN   AssessmentAttempt #{att.pk} → "
                        f"AssessmentSetVersion #{version.pk} (v{version.version_number})"
                    )

                if not dry_run:
                    with transaction.atomic():
                        AssessmentAttempt.objects.filter(
                            pk=att.pk, set_version_id__isnull=True
                        ).update(set_version=version)
                        emit_governance_event(
                            event_type=GovernanceEvent.EVENT_ATTEMPT_SNAPSHOT_PIN,
                            actor=None,
                            entity_type="AssessmentAttempt",
                            entity_id=att.pk,
                            payload={
                                "set_id": hw.assessment_set_id,
                                "pinned_version_id": version.pk,
                                "pinned_version_number": version.version_number,
                                "source": "backfill_snapshot_versions",
                                "snapshot_pinned": True,
                            },
                        )
                pinned += 1

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  ERROR AssessmentAttempt #{att.pk}: {exc}")
                )
                errors += 1

        return pinned, skipped, errors
