"""Offline check for subject / UserAccess / PracticeTest consistency (ops + CI)."""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from access import constants as C
from access.models import UserAccess
from access.services import user_domain_subject
from exams.models import PracticeTest
from users.models import User


class Command(BaseCommand):
    help = "Report RBAC data integrity issues (staff UserAccess, PracticeTest.subject, role/subject rules)."

    def handle(self, *args, **options):
        exit_code = 0
        n = 0

        bad_tests = PracticeTest.objects.exclude(
            subject__in=(C.SUBJECT_MATH_PLATFORM, C.SUBJECT_ENGLISH_PLATFORM)
        )
        for pt in bad_tests.iterator():
            n += 1
            exit_code = 1
            self.stderr.write(
                self.style.ERROR(
                    f"[PracticeTest] id={pt.pk} invalid subject={pt.subject!r}"
                )
            )

        for u in User.objects.filter(role=C.ROLE_TEACHER).iterator():
            dom = user_domain_subject(u)
            if dom not in C.ALL_DOMAIN_SUBJECTS:
                n += 1
                exit_code = 1
                self.stderr.write(
                    self.style.ERROR(
                        f"[User] teacher id={u.pk} missing or invalid subject field"
                    )
                )
                continue
            if not UserAccess.objects.filter(
                user_id=u.pk, subject=dom, classroom_id__isnull=True
            ).exists():
                n += 1
                exit_code = 1
                self.stderr.write(
                    self.style.ERROR(
                        f"[UserAccess] teacher id={u.pk} missing global row for subject={dom!r}"
                    )
                )

        for u in User.objects.filter(role__in=(C.ROLE_ADMIN, C.ROLE_TEST_ADMIN)).iterator():
            raw = getattr(u, "subject", None)
            if raw not in (None, ""):
                n += 1
                exit_code = 1
                self.stderr.write(
                    self.style.ERROR(
                        f"[User] id={u.pk} role={u.role!r} must not have subject set (got {raw!r})"
                    )
                )

        for u in User.objects.filter(role=C.ROLE_SUPER_ADMIN).exclude(subject__isnull=True).exclude(subject="").iterator():
            n += 1
            exit_code = 1
            self.stderr.write(
                self.style.ERROR(
                    f"[User] super_admin id={u.pk} must not have subject set (got {u.subject!r})"
                )
            )

        for u in User.objects.filter(role=C.ROLE_STUDENT).exclude(subject__isnull=True).exclude(subject="").iterator():
            n += 1
            exit_code = 1
            self.stderr.write(
                self.style.ERROR(
                    f"[User] student id={u.pk} must not have subject set (got {u.subject!r})"
                )
            )

        if exit_code == 0:
            self.stdout.write(self.style.SUCCESS("access integrity: no issues found."))
        else:
            self.stderr.write(self.style.WARNING(f"access integrity: {n} issue(s) reported."))
        sys.exit(exit_code)
