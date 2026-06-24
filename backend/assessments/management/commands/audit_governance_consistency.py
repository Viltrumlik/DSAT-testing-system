"""
Management command: audit_governance_consistency

Scans all assessment records for governance inconsistencies:

CHECK 1 — Missing snapshot pins on HomeworkAssignment
  HomeworkAssignment rows with set_version_id=NULL for a set that HAS
  published versions. These assignments are in the fallback path and
  should be backfilled.

CHECK 2 — Missing snapshot pins on AssessmentAttempt
  AssessmentAttempt rows with set_version_id=NULL whose homework has a
  set_version. The version should have been inherited at attempt creation.

CHECK 3 — Version mismatch between homework and attempt
  AssessmentAttempt.set_version_id != homework.set_version_id (and neither
  is NULL). This could indicate a bug in StartAttemptView.

CHECK 4 — Orphan version references
  AssessmentAttempt or HomeworkAssignment references a set_version that
  belongs to a different assessment_set than the homework's assessment_set.

CHECK 5 — Snapshot checksum integrity
  Re-verify checksums on AssessmentSetVersion rows (subset).
  Full verification: use check_snapshot_integrity instead.

CHECK 6 — Missing governance events
  Published AssessmentSetVersion rows that have no corresponding
  GovernanceEvent(event_type=publish). These were created before the
  governance event system or by a bypass.

CHECK 7 — Fallback usage rate
  How many graded attempts are still using the live-read fallback path.
  Target: 0%.

Usage:
    python manage.py audit_governance_consistency
    python manage.py audit_governance_consistency --checks 1,2,3
    python manage.py audit_governance_consistency --fail-on-issue
    python manage.py audit_governance_consistency --set-id 42
    python manage.py audit_governance_consistency --emit-alert
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Audit governance consistency across assessment records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--checks",
            type=str,
            default="all",
            help="Comma-separated check numbers to run (1-7), or 'all'.",
        )
        parser.add_argument(
            "--fail-on-issue",
            action="store_true",
            default=False,
            help="Exit code 1 if any issues are found.",
        )
        parser.add_argument(
            "--set-id",
            type=int,
            default=None,
            help="Restrict checks to this AssessmentSet PK.",
        )
        parser.add_argument(
            "--emit-alert",
            action="store_true",
            default=False,
            help="Emit GovernanceEvent(EVENT_INTEGRITY_FAILURE) for each issue found.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Only print the summary table, suppress per-issue rows.",
        )

    def handle(self, *args, **options):
        checks_arg = options["checks"]
        fail_on_issue = options["fail_on_issue"]
        set_id = options["set_id"]
        emit_alert = options["emit_alert"]
        quiet = options["quiet"]

        if checks_arg == "all":
            enabled = {1, 2, 3, 4, 5, 6, 7}
        else:
            try:
                enabled = {int(x.strip()) for x in checks_arg.split(",")}
            except ValueError:
                raise CommandError("--checks must be comma-separated integers or 'all'")

        total_issues = 0
        results: list[tuple[int, str, int]] = []  # (check#, label, issue_count)

        check_map = {
            1: ("Missing HW snapshot pins", self._check1_hw_missing_pins),
            2: ("Missing attempt snapshot pins", self._check2_attempt_missing_pins),
            3: ("HW/attempt version mismatch", self._check3_version_mismatch),
            4: ("Orphan version references", self._check4_orphan_references),
            5: ("Snapshot checksum integrity", self._check5_checksum_integrity),
            6: ("Missing publish governance events", self._check6_missing_gov_events),
            7: ("Fallback usage rate", self._check7_fallback_rate),
        }

        for n in sorted(enabled):
            label, fn = check_map[n]
            if not quiet:
                self.stdout.write(f"\n── Check {n}: {label} ──")
            try:
                issues = fn(set_id=set_id, quiet=quiet, emit_alert=emit_alert)
                total_issues += issues
                results.append((n, label, issues))
                status = self.style.ERROR(f"{issues} issues") if issues else self.style.SUCCESS("OK")
                if not quiet or issues:
                    self.stdout.write(f"  Check {n} result: {status}")
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  Check {n} ERROR: {exc}"))
                results.append((n, label, -1))  # -1 = errored

        # ── Summary table ──────────────────────────────────────────────────────
        self.stdout.write("\n" + "─" * 55)
        self.stdout.write(f"{'Check':<8} {'Label':<38} {'Issues':>6}")
        self.stdout.write("─" * 55)
        for n, label, cnt in results:
            cnt_str = self.style.ERROR(str(cnt)) if cnt > 0 else self.style.SUCCESS("0")
            self.stdout.write(f"{n:<8} {label:<38} {cnt_str:>6}")
        self.stdout.write("─" * 55)
        total_style = self.style.ERROR if total_issues else self.style.SUCCESS
        self.stdout.write(f"{'TOTAL':<47} {total_style(str(total_issues)):>6}")

        if fail_on_issue and total_issues > 0:
            raise SystemExit(1)

    # ── Check implementations ──────────────────────────────────────────────────

    def _check1_hw_missing_pins(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import HomeworkAssignment, AssessmentSetVersion
        qs = HomeworkAssignment.objects.filter(set_version_id__isnull=True)
        if set_id:
            qs = qs.filter(assessment_set_id=set_id)
        issues = 0
        for hw in qs.iterator(chunk_size=500):
            has_versions = AssessmentSetVersion.objects.filter(
                assessment_set_id=hw.assessment_set_id
            ).exists()
            if has_versions:
                issues += 1
                if not quiet:
                    self.stdout.write(
                        f"  ISSUE hw#{hw.pk} set#{hw.assessment_set_id}: "
                        "has published versions but set_version_id=NULL. "
                        "Run backfill_snapshot_versions."
                    )
                if emit_alert:
                    self._emit_issue_event(
                        entity_type="HomeworkAssignment",
                        entity_id=hw.pk,
                        description="Missing snapshot pin — published versions exist",
                    )
        return issues

    def _check2_attempt_missing_pins(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentAttempt
        qs = (
            AssessmentAttempt.objects.filter(
                set_version_id__isnull=True,
                homework__set_version_id__isnull=False,
            )
            .select_related("homework")
        )
        if set_id:
            qs = qs.filter(homework__assessment_set_id=set_id)
        issues = 0
        for att in qs.iterator(chunk_size=500):
            issues += 1
            if not quiet:
                self.stdout.write(
                    f"  ISSUE attempt#{att.pk} hw#{att.homework_id}: "
                    "homework has set_version but attempt.set_version_id=NULL. "
                    "Run backfill_snapshot_versions --attempt-only."
                )
            if emit_alert:
                self._emit_issue_event(
                    entity_type="AssessmentAttempt",
                    entity_id=att.pk,
                    description="Missing snapshot pin — homework has version",
                )
        return issues

    def _check3_version_mismatch(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentAttempt
        qs = (
            AssessmentAttempt.objects.filter(
                set_version_id__isnull=False,
                homework__set_version_id__isnull=False,
            )
            .select_related("homework")
            .exclude(set_version_id=models_set_version_id_ref())
        )
        # Can't use field reference in .exclude() cleanly — use Python filter
        from assessments.models import AssessmentAttempt as _AT
        qs = _AT.objects.filter(
            set_version_id__isnull=False,
            homework__set_version_id__isnull=False,
        ).select_related("homework")
        if set_id:
            qs = qs.filter(homework__assessment_set_id=set_id)

        issues = 0
        for att in qs.iterator(chunk_size=500):
            if att.set_version_id != att.homework.set_version_id:
                issues += 1
                if not quiet:
                    self.stdout.write(
                        f"  ISSUE attempt#{att.pk}: "
                        f"set_version_id={att.set_version_id} != "
                        f"homework.set_version_id={att.homework.set_version_id}. "
                        "Possible bug in StartAttemptView."
                    )
                if emit_alert:
                    self._emit_issue_event(
                        entity_type="AssessmentAttempt",
                        entity_id=att.pk,
                        description=f"Version mismatch with homework: "
                                    f"att={att.set_version_id} hw={att.homework.set_version_id}",
                    )
        return issues

    def _check4_orphan_references(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentAttempt, HomeworkAssignment
        issues = 0

        hw_qs = HomeworkAssignment.objects.filter(set_version_id__isnull=False).select_related(
            "set_version"
        )
        if set_id:
            hw_qs = hw_qs.filter(assessment_set_id=set_id)
        for hw in hw_qs.iterator(chunk_size=500):
            if hw.set_version.assessment_set_id != hw.assessment_set_id:
                issues += 1
                if not quiet:
                    self.stdout.write(
                        f"  ISSUE hw#{hw.pk}: set_version belongs to "
                        f"set#{hw.set_version.assessment_set_id} but homework is for "
                        f"set#{hw.assessment_set_id}. ORPHAN REFERENCE."
                    )

        att_qs = AssessmentAttempt.objects.filter(set_version_id__isnull=False).select_related(
            "set_version", "homework"
        )
        if set_id:
            att_qs = att_qs.filter(homework__assessment_set_id=set_id)
        for att in att_qs.iterator(chunk_size=500):
            if att.set_version.assessment_set_id != att.homework.assessment_set_id:
                issues += 1
                if not quiet:
                    self.stdout.write(
                        f"  ISSUE attempt#{att.pk}: set_version belongs to "
                        f"set#{att.set_version.assessment_set_id} but attempt is for "
                        f"set#{att.homework.assessment_set_id}. ORPHAN REFERENCE."
                    )

        return issues

    def _check5_checksum_integrity(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentSetVersion
        from assessments.domain.snapshot_builder import verify_snapshot_integrity

        qs = AssessmentSetVersion.objects.all()
        if set_id:
            qs = qs.filter(assessment_set_id=set_id)

        issues = 0
        for v in qs.iterator(chunk_size=100):
            if not verify_snapshot_integrity(v.snapshot_json, v.snapshot_checksum):
                issues += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  INTEGRITY FAIL version#{v.pk} set#{v.assessment_set_id} "
                        f"v{v.version_number}: checksum mismatch. "
                        "CRITICAL — this snapshot may have been corrupted."
                    )
                )
                if emit_alert:
                    self._emit_issue_event(
                        entity_type="AssessmentSetVersion",
                        entity_id=v.pk,
                        description=f"Snapshot checksum mismatch (v{v.version_number})",
                    )
        return issues

    def _check6_missing_gov_events(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentSetVersion, GovernanceEvent

        qs = AssessmentSetVersion.objects.all()
        if set_id:
            qs = qs.filter(assessment_set_id=set_id)

        published_ids = set(qs.values_list("pk", flat=True))
        events_with_publish = set(
            GovernanceEvent.objects.filter(
                event_type=GovernanceEvent.EVENT_PUBLISH,
                entity_type="AssessmentSetVersion",
                entity_id__in=published_ids,
            ).values_list("entity_id", flat=True)
        )

        missing = published_ids - events_with_publish
        if missing and not quiet:
            for vid in sorted(missing):
                self.stdout.write(
                    f"  ISSUE version#{vid}: no publish governance event. "
                    "Created before governance event system or via bypass."
                )
        return len(missing)

    def _check7_fallback_rate(self, *, set_id, quiet, emit_alert) -> int:
        from assessments.models import AssessmentAttempt, GovernanceEvent

        total_graded = AssessmentAttempt.objects.filter(
            status=AssessmentAttempt.STATUS_GRADED
        )
        if set_id:
            total_graded = total_graded.filter(homework__assessment_set_id=set_id)
        total = total_graded.count()

        fallback_events = GovernanceEvent.objects.filter(
            event_type=GovernanceEvent.EVENT_FALLBACK_PATH_USED
        )
        if set_id:
            fallback_events = fallback_events.filter(
                payload__set_id=set_id
            )
        fallback_count = fallback_events.count()

        no_version = total_graded.filter(set_version_id__isnull=True).count()

        if not quiet:
            pct = (no_version / total * 100) if total else 0
            self.stdout.write(
                f"  Graded attempts: {total} total, "
                f"{no_version} without snapshot ({pct:.1f}% fallback exposure)"
            )
            self.stdout.write(f"  Fallback events recorded: {fallback_count}")
            if no_version == 0:
                self.stdout.write(self.style.SUCCESS("  ✓ 100% snapshot coverage — fallback path can be sunset."))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ {no_version} attempts without snapshot. "
                        "Run backfill_snapshot_versions to reduce exposure."
                    )
                )
        return no_version  # treat each un-snapshotted graded attempt as an issue

    def _emit_issue_event(self, *, entity_type: str, entity_id: int, description: str) -> None:
        from assessments.domain.governance_events import emit_governance_event
        from assessments.models import GovernanceEvent
        emit_governance_event(
            event_type=GovernanceEvent.EVENT_INTEGRITY_FAILURE,
            actor=None,
            entity_type=entity_type,
            entity_id=entity_id,
            payload={
                "description": description,
                "source": "audit_governance_consistency",
            },
        )


def models_set_version_id_ref():
    """Dummy — see check3 comment for why we use Python filter."""
    return None
