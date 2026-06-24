"""
Backfill legacy access into ResourceAccessGrant (migration Stage 2).

Idempotent and resumable: re-running creates no duplicates (active-grant dedup).
Backfilled grants carry ``source=SYSTEM`` and a ``BACKFILLED`` audit event.

    python manage.py access_backfill --dry-run     # counts only, no writes
    python manage.py access_backfill               # apply
    python manage.py access_backfill --undo        # remove backfilled-only grants

Safe to run with all feature flags off; it only writes the new tables.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from access.engine.access_service import AccessService
from access.models import AccessGrantEvent, ResourceAccessGrant
from access import resources


class Command(BaseCommand):
    help = "Backfill legacy UserAccess + assigned_users M2Ms into ResourceAccessGrant."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--undo", action="store_true")
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **opts):
        if opts["undo"]:
            return self._undo(dry_run=opts["dry_run"])

        dry = opts["dry_run"]
        counts = {"subject": 0, "practice_test": 0, "mock_exam": 0, "portal_mock": 0, "assignment": 0}

        counts["subject"] = self._backfill_user_access(dry)
        counts["practice_test"] = self._backfill_m2m(
            "exams.PracticeTest", resources.RT_PRACTICE_TEST, dry
        )
        counts["mock_exam"] = self._backfill_m2m("exams.MockExam", resources.RT_MOCK_EXAM, dry)
        counts["portal_mock"] = self._backfill_portal_mock(dry)
        counts["assignment"] = self._backfill_class_assignments(dry)

        prefix = "[dry-run] would create" if dry else "created"
        for k, v in counts.items():
            self.stdout.write(f"{prefix} {v} grant(s) from {k}")
        self.stdout.write(self.style.SUCCESS(f"{prefix} {sum(counts.values())} grant(s) total"))

    # -- sources ---------------------------------------------------------

    def _backfill_user_access(self, dry) -> int:
        from access.models import UserAccess

        n = 0
        for ua in UserAccess.objects.all().iterator(chunk_size=500):
            source = (
                ResourceAccessGrant.SOURCE_CLASSROOM
                if ua.classroom_id
                else ResourceAccessGrant.SOURCE_MANUAL
            )
            if dry:
                if not self._subject_exists(ua.user_id, ua.subject, ua.classroom_id):
                    n += 1
                continue
            before = ResourceAccessGrant.objects.count()
            AccessService.grant_subject(
                ua.user, ua.subject, source=ResourceAccessGrant.SOURCE_SYSTEM,
                granted_by=ua.granted_by, classroom=ua.classroom_id,
                note=f"backfill (orig source={source})",
                _event=AccessGrantEvent.ACTION_BACKFILLED,
            )
            n += ResourceAccessGrant.objects.count() - before
        return n

    def _backfill_m2m(self, model_label, resource_type, dry) -> int:
        from django.apps import apps as dj_apps

        app_label, model_name = model_label.split(".")
        Model = dj_apps.get_model(app_label, model_name)
        n = 0
        for obj in Model.objects.all().iterator(chunk_size=200):
            for user in obj.assigned_users.all().iterator(chunk_size=500):
                n += self._ensure_resource(user, resource_type, obj.pk, dry)
        return n

    def _backfill_portal_mock(self, dry) -> int:
        from exams.models import PortalMockExam

        n = 0
        for portal in PortalMockExam.objects.select_related("mock_exam").iterator(chunk_size=200):
            if not portal.mock_exam_id:
                continue
            for user in portal.assigned_users.all().iterator(chunk_size=500):
                n += self._ensure_resource(user, resources.RT_MOCK_EXAM, portal.mock_exam_id, dry)
        return n

    def _backfill_class_assignments(self, dry) -> int:
        """Classroom homework targets -> CLASSROOM resource grants for enrolled students."""
        from classes.models import (
            Assignment,
            ClassroomMembership,
            assignment_target_practice_test_ids,
        )

        n = 0
        for a in Assignment.objects.select_related("classroom").iterator(chunk_size=200):
            student_ids = list(
                a.classroom.memberships.filter(
                    role=ClassroomMembership.ROLE_STUDENT
                ).values_list("user_id", flat=True)
            )
            if not student_ids:
                continue
            from django.contrib.auth import get_user_model

            User = get_user_model()
            users = list(User.objects.filter(pk__in=student_ids))

            targets: list[tuple[str, int]] = []
            for pt_id in assignment_target_practice_test_ids(a):
                targets.append((resources.RT_PRACTICE_TEST, pt_id))
            if a.mock_exam_id:
                targets.append((resources.RT_MOCK_EXAM, a.mock_exam_id))
            if getattr(a, "practice_test_pack_id", None):
                targets.append((resources.RT_PRACTICE_TEST_PACK, a.practice_test_pack_id))

            for rt, rid in targets:
                for user in users:
                    n += self._ensure_resource(
                        user, rt, rid, dry,
                        source=ResourceAccessGrant.SOURCE_CLASSROOM, classroom=a.classroom_id,
                    )
        return n

    # -- helpers ---------------------------------------------------------

    def _ensure_resource(self, user, resource_type, resource_id, dry, *, source=None, classroom=None) -> int:
        if dry:
            return 0 if self._resource_exists(user.pk, resource_type, resource_id, classroom) else 1
        before = ResourceAccessGrant.objects.count()
        AccessService.grant_resource(
            user, resource_type, resource_id,
            source=ResourceAccessGrant.SOURCE_SYSTEM if source is None else source,
            classroom=classroom, note="backfill",
            _event=AccessGrantEvent.ACTION_BACKFILLED,
        )
        return ResourceAccessGrant.objects.count() - before

    @staticmethod
    def _subject_exists(user_id, subject, classroom_id) -> bool:
        return ResourceAccessGrant.objects.filter(
            user_id=user_id, scope=ResourceAccessGrant.SCOPE_SUBJECT, subject=subject,
            classroom_id=classroom_id, status=ResourceAccessGrant.STATUS_ACTIVE,
        ).exists()

    @staticmethod
    def _resource_exists(user_id, resource_type, resource_id, classroom_id) -> bool:
        return ResourceAccessGrant.objects.filter(
            user_id=user_id, scope=ResourceAccessGrant.SCOPE_RESOURCE,
            resource_type=resource_type, resource_id=resource_id,
            classroom_id=classroom_id, status=ResourceAccessGrant.STATUS_ACTIVE,
        ).exists()

    # -- undo ------------------------------------------------------------

    def _undo(self, *, dry_run) -> None:
        """Delete SYSTEM grants whose only audit events are BACKFILLED (no human action)."""
        from django.db.models import Count, Q

        candidates = (
            ResourceAccessGrant.objects.filter(source=ResourceAccessGrant.SOURCE_SYSTEM)
            .annotate(
                _total=Count("events"),
                _backfilled=Count("events", filter=Q(events__action=AccessGrantEvent.ACTION_BACKFILLED)),
            )
            .filter(_total__gt=0, _total=models_F("_backfilled"))
        )
        n = candidates.count()
        if dry_run:
            self.stdout.write(f"[dry-run] would delete {n} backfilled-only grant(s)")
            return
        with transaction.atomic():
            ids = list(candidates.values_list("pk", flat=True))
            ResourceAccessGrant.objects.filter(pk__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(f"deleted {n} backfilled-only grant(s)"))


def models_F(name):
    from django.db.models import F

    return F(name)
