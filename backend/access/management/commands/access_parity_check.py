"""
Parity check (migration Stage 3): legacy student visibility vs VisibilityService.

Samples (student × resource) pairs and asserts the new engine agrees with the
legacy per-resource gate. Exits non-zero on any mismatch and prints offenders, so
it can gate the read cutover in CI / pre-deploy.

    python manage.py access_parity_check --resource-type practice_test --limit 2000

Legacy oracle (student): visible iff the student is in the resource's
``assigned_users`` M2M, OR legacy subject access covers the resource's subject(s).
Only resource types that carry an ``assigned_users`` M2M are checked.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from access import constants, resources
from access.engine import VisibilityService
from access.services import has_global_subject_access, normalized_role

_M2M_TYPES = {
    resources.RT_PRACTICE_TEST: "exams.PracticeTest",
    resources.RT_MOCK_EXAM: "exams.MockExam",
}


class Command(BaseCommand):
    help = "Compare legacy student visibility with the new VisibilityService."

    def add_arguments(self, parser):
        parser.add_argument("--resource-type", default=resources.RT_PRACTICE_TEST)
        parser.add_argument("--limit", type=int, default=1000, help="max pairs to check")
        parser.add_argument("--users", type=int, default=200, help="max students to sample")

    def handle(self, *args, **opts):
        rtype = opts["resource_type"]
        if rtype not in _M2M_TYPES:
            raise CommandError(
                f"--resource-type must be one of: {', '.join(sorted(_M2M_TYPES))}"
            )
        rt = resources.get(rtype)
        Model = rt.model()
        User = get_user_model()

        students = [
            u for u in User.objects.all()[: opts["users"] * 3]
            if normalized_role(u) == constants.ROLE_STUDENT
        ][: opts["users"]]
        objects = list(Model.objects.all()[:500])

        checked = mismatches = 0
        offenders: list[str] = []
        for u in students:
            for obj in objects:
                if checked >= opts["limit"]:
                    break
                legacy = self._legacy_can_see(u, rtype, obj)
                new = VisibilityService.can_access(u, rtype, obj.pk, instance=obj)
                checked += 1
                if legacy != new:
                    mismatches += 1
                    if len(offenders) < 50:
                        offenders.append(
                            f"user={u.pk} {rtype}#{obj.pk} legacy={legacy} new={new}"
                        )
            if checked >= opts["limit"]:
                break

        self.stdout.write(f"checked {checked} pair(s); {mismatches} mismatch(es)")
        for line in offenders:
            self.stdout.write(self.style.WARNING("  " + line))
        if mismatches:
            raise CommandError(f"parity FAILED: {mismatches} mismatch(es)")
        self.stdout.write(self.style.SUCCESS("parity OK"))

    def _legacy_can_see(self, user, rtype, obj) -> bool:
        if user in obj.assigned_users.all():
            return True
        for dom in resources.get(rtype).domain_subjects(obj):
            if has_global_subject_access(user, dom):
                return True
        return False
