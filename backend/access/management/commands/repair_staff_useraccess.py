"""Create missing global UserAccess rows for staff accounts (optional auto-repair)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from access import constants as C
from access.models import UserAccess
from access.services import user_domain_subject

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Ensure each **teacher** with a valid domain subject has a global (classroom=NULL) "
        "UserAccess row. Admin/test_admin are global and do not use self-subject rows. "
        "Use --apply to write; default is dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist fixes. Without this flag, only prints planned actions.",
        )

    def handle(self, *args, **options):
        apply_fix = options["apply"]
        planned = 0
        for u in User.objects.filter(role=C.ROLE_TEACHER).iterator():
            dom = user_domain_subject(u)
            if dom not in C.ALL_DOMAIN_SUBJECTS:
                continue
            if UserAccess.objects.filter(
                user_id=u.pk, subject=dom, classroom_id__isnull=True
            ).exists():
                continue
            planned += 1
            self.stdout.write(
                f"{'CREATE' if apply_fix else 'would create'} UserAccess user_id={u.pk} "
                f"subject={dom!r} global"
            )
            if apply_fix:
                with transaction.atomic():
                    UserAccess.objects.get_or_create(
                        user=u,
                        subject=dom,
                        classroom=None,
                        defaults={"granted_by": u},
                    )
        if planned == 0:
            self.stdout.write(self.style.SUCCESS("repair_staff_useraccess: nothing to do."))
        elif not apply_fix:
            self.stdout.write(
                self.style.WARNING(
                    f"repair_staff_useraccess: {planned} row(s) missing — re-run with --apply to fix."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"repair_staff_useraccess: created/verified {planned} row(s).")
            )
