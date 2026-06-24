from __future__ import annotations

import json
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from exams.engine_integrity import infer_state_from_attempt, required_module_orders_for_test
from exams.metrics import incr as metric_incr
from exams.models import Module, PracticeTest, Question, TestAttempt, ensure_full_mock_practice_test_modules


class Command(BaseCommand):
    help = "Repair SAT testing engine integrity issues (safe, idempotent, minimal)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be changed.")
        parser.add_argument("--limit", type=int, default=2000, help="Max objects to touch per category.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary.")
        parser.add_argument(
            "--fix-timers",
            action="store_true",
            help="Also normalize non-positive module timers to expected defaults (or midterm config).",
        )
        parser.add_argument(
            "--fix-question-orders",
            action="store_true",
            help="Dense-reindex Questions in modules violating UNIQUE(module_id, order).",
        )

    def handle(self, *args, **options):
        dry = bool(options["dry_run"])
        limit = int(options["limit"] or 2000)
        as_json = bool(options["json"])
        fix_timers = bool(options["fix_timers"])
        fix_question_orders = bool(options["fix_question_orders"])

        summary = defaultdict(lambda: {"count": 0, "ids": []})

        def _bump(kind: str, obj_id: int | None = None):
            summary[kind]["count"] += 1
            if obj_id is not None and len(summary[kind]["ids"]) < 50:
                summary[kind]["ids"].append(int(obj_id))

        # ── 1) PracticeTests missing required modules ───────────────────────
        tests = (
            PracticeTest.objects.select_related("mock_exam")
            .prefetch_related("modules")
            .all()
        )
        touched_tests = 0
        for t in tests.iterator(chunk_size=200):
            required = required_module_orders_for_test(t)
            existing = {m.module_order for m in list(t.modules.all())}
            if any(o not in existing for o in required):
                _bump("practice_test.missing_required_modules", t.pk)
                if not dry:
                    ensure_full_mock_practice_test_modules(t)
                touched_tests += 1
                if touched_tests >= limit:
                    break

        # ── 2) Duplicate module_order rows: merge questions into canonical ──
        dup_rows = (
            Module.objects.values("practice_test_id", "module_order")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .order_by("practice_test_id", "module_order")
        )
        dup_touched = 0
        for row in dup_rows.iterator(chunk_size=200):
            if dup_touched >= limit:
                break
            pt_id = row["practice_test_id"]
            order = row["module_order"]
            mods = list(Module.objects.filter(practice_test_id=pt_id, module_order=order).order_by("id"))
            if len(mods) <= 1:
                continue
            primary = mods[0]
            extras = mods[1:]
            _bump("module.duplicate_module_order_group", primary.pk)

            if dry:
                dup_touched += 1
                continue

            with transaction.atomic():
                # Move questions
                Question.objects.filter(module__in=extras).update(module=primary)
                # Move completed_modules M2M references:
                # If attempts completed an extra module row, also add primary to completed_modules.
                for extra in extras:
                    for att_id in TestAttempt.completed_modules.through.objects.filter(module_id=extra.pk).values_list("testattempt_id", flat=True).iterator():
                        TestAttempt.completed_modules.through.objects.get_or_create(
                            testattempt_id=att_id, module_id=primary.pk
                        )
                # Delete extras (attempt.current_module is SET_NULL; will be repaired later)
                Module.objects.filter(id__in=[m.pk for m in extras]).delete()

            dup_touched += 1

        # ── 3) Invalid module_order values ──────────────────────────────────
        invalid_mods = Module.objects.exclude(module_order__in=[1, 2]).order_by("id")[:limit]
        for m in invalid_mods:
            _bump("module.invalid_module_order", m.pk)
            if dry:
                continue
            # Try to place into a free slot on the same test, otherwise clamp to 1.
            existing = set(Module.objects.filter(practice_test_id=m.practice_test_id).values_list("module_order", flat=True))
            new_order = 1 if 1 not in existing else (2 if 2 not in existing else 1)
            m.module_order = new_order
            m.save(update_fields=["module_order"])

        # ── 4) Fix non-positive timers (optional) ───────────────────────────
        if fix_timers:
            bad_timers = Module.objects.filter(time_limit_minutes__lte=0).select_related("practice_test", "practice_test__mock_exam").order_by("id")[:limit]
            for m in bad_timers:
                _bump("module.non_positive_time_limit", m.pk)
                if dry:
                    continue
                # Re-run provisioning logic to determine expected minutes.
                # If the module already exists, mimic ensure_full logic for minutes.
                test = m.practice_test
                mock = getattr(test, "mock_exam", None)
                mins = 32 if test.subject == "READING_WRITING" else 35
                if mock and getattr(mock, "kind", None) == "MIDTERM":
                    if m.module_order == 1:
                        mins = int(getattr(mock, "midterm_module1_minutes", 60) or 60)
                    else:
                        mins = int(getattr(mock, "midterm_module2_minutes", 60) or 60)
                m.time_limit_minutes = max(1, int(mins))
                m.save(update_fields=["time_limit_minutes"])

        # ── 5) Attempts with impossible states / pointers ───────────────────
        # Repair strategy:
        # - If active but current_module is null: snap to required module row based on state.
        # - If state contradicts is_completed: normalize to COMPLETED.
        # - If state/module mismatch: infer fresh state and reset current_module accordingly.
        attempts = (
            TestAttempt.objects.select_related("practice_test", "current_module", "practice_test__mock_exam")
            .prefetch_related("completed_modules")
            .order_by("id")
        )
        touched_attempts = 0
        now = timezone.now()
        for att in attempts.iterator(chunk_size=200):
            if touched_attempts >= limit:
                break

            before = (att.current_state, att.is_completed, att.current_module_id)

            desired_state = att.current_state
            desired_is_completed = att.is_completed
            desired_current_module_id = att.current_module_id

            # Normalize completed flags.
            if att.is_completed and att.current_state != TestAttempt.STATE_COMPLETED:
                desired_state = TestAttempt.STATE_COMPLETED
            if att.current_state == TestAttempt.STATE_COMPLETED and not att.is_completed:
                desired_is_completed = True

            # If active but module missing/mismatched, snap by state.
            if desired_state in (TestAttempt.STATE_MODULE_1_ACTIVE, TestAttempt.STATE_MODULE_2_ACTIVE):
                ensure_full_mock_practice_test_modules(att.practice_test)
                order = 1 if desired_state == TestAttempt.STATE_MODULE_1_ACTIVE else 2
                mod = att.practice_test.modules.filter(module_order=order).order_by("id").first()
                desired_current_module_id = mod.pk if mod else None

            # If scoring/completed, ensure current_module null.
            if desired_state in (TestAttempt.STATE_SCORING, TestAttempt.STATE_COMPLETED):
                desired_current_module_id = None

            # If still inconsistent, infer.
            cm_order = getattr(att.current_module, "module_order", None) if att.current_module else None
            if desired_state == TestAttempt.STATE_MODULE_1_ACTIVE and cm_order not in (None, 1):
                desired_state = infer_state_from_attempt(att)
            if desired_state == TestAttempt.STATE_MODULE_2_ACTIVE and cm_order not in (None, 2):
                desired_state = infer_state_from_attempt(att)

            after = (desired_state, desired_is_completed, desired_current_module_id)
            if after == before:
                continue

            _bump("attempt.repaired", att.pk)
            touched_attempts += 1
            if dry:
                continue

            with transaction.atomic():
                locked = TestAttempt.objects.select_for_update().get(pk=att.pk)
                updates = {}
                if locked.current_state != desired_state:
                    updates["current_state"] = desired_state
                    locked.current_state = desired_state
                if locked.is_completed != desired_is_completed:
                    updates["is_completed"] = desired_is_completed
                    locked.is_completed = desired_is_completed
                if locked.current_module_id != desired_current_module_id:
                    updates["current_module_id"] = desired_current_module_id
                    locked.current_module_id = desired_current_module_id
                if desired_is_completed and not locked.completed_at:
                    locked.completed_at = now
                    updates["completed_at"] = now

                if updates:
                    locked.version_number = int(locked.version_number or 0) + 1
                    updates["version_number"] = locked.version_number
                    locked.save(update_fields=list(updates.keys()) + ["updated_at"])

        # ── 6) Duplicate active attempts per (student, practice_test) ───────
        # Repair strategy:
        # - Choose canonical attempt as the most recently updated (tie-breaker: highest id).
        # - Mark all other active attempts in that group as ABANDONED and clear pointers.
        dup_groups = (
            TestAttempt.objects.filter(is_completed=False)
            .exclude(current_state=TestAttempt.STATE_ABANDONED)
            .values("student_id", "practice_test_id")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .order_by("student_id", "practice_test_id")
        )
        dup_touched = 0
        for g in dup_groups.iterator(chunk_size=200):
            if dup_touched >= limit:
                break
            student_id = g["student_id"]
            test_id = g["practice_test_id"]
            attempts = list(
                TestAttempt.objects.filter(
                    student_id=student_id,
                    practice_test_id=test_id,
                    is_completed=False,
                )
                .exclude(current_state=TestAttempt.STATE_ABANDONED)
                .order_by("-updated_at", "-id")
            )
            if len(attempts) <= 1:
                continue

            canonical = attempts[0]
            extras = attempts[1:]
            _bump("attempt.duplicate_active_group", canonical.pk)
            dup_touched += 1

            if dry:
                continue

            with transaction.atomic():
                for extra in extras:
                    locked = TestAttempt.objects.select_for_update().get(pk=extra.pk)
                    locked.abandoned_checkpoint_state = str(getattr(locked, "current_state", "") or "")
                    locked.current_state = TestAttempt.STATE_ABANDONED
                    locked.current_module = None
                    locked.current_module_start_time = None
                    locked.version_number = int(locked.version_number or 0) + 1
                    locked.save(
                        update_fields=[
                            "abandoned_checkpoint_state",
                            "current_state",
                            "current_module",
                            "current_module_start_time",
                            "version_number",
                            "updated_at",
                        ]
                    )
                    metric_incr("integrity_repairs_applied")

        # ── 7) Persisted MODULE_*_SUBMITTED (no longer healed via HTTP resume) ─
        legacy_sub_ids = list(
            TestAttempt.objects.filter(
                is_completed=False,
                current_state__in=(
                    TestAttempt.STATE_MODULE_1_SUBMITTED,
                    TestAttempt.STATE_MODULE_2_SUBMITTED,
                ),
            ).values_list("pk", flat=True)[:limit]
        )
        for leg_pk in legacy_sub_ids:
            _bump("attempt.legacy_submitted_seen", leg_pk)
            if dry:
                continue
            try:
                with transaction.atomic():
                    locked = TestAttempt.objects.select_for_update().get(pk=leg_pk)
                    if locked.current_state not in (
                        TestAttempt.STATE_MODULE_1_SUBMITTED,
                        TestAttempt.STATE_MODULE_2_SUBMITTED,
                    ):
                        continue
                    locked.repair_legacy_submitted_states()
                    metric_incr("integrity_repairs_applied")
            except Exception:
                _bump("attempt.legacy_submitted_repair_failed", leg_pk)

        # ── 8) Question (module_id, order) UNIQUE violations ─────────────────────
        if fix_question_orders:
            from exams.question_integrity import question_duplicate_order_counts, repair_modules_with_duplicate_orders

            affected = sorted({m for (m, _ord) in question_duplicate_order_counts()})
            for mid in affected[:limit]:
                _bump("question.duplicate_order_module", mid)

            if not dry and affected:
                repair_modules_with_duplicate_orders(limit=limit)
                metric_incr("integrity_repairs_applied")

        out = dict(summary)
        if as_json:
            self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
            return

        self.stdout.write("EXAM INTEGRITY REPAIR")
        self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
        if dry:
            self.stdout.write("dry_run=True (no changes applied)")

