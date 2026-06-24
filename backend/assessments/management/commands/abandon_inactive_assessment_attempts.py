from __future__ import annotations

from django.core.management.base import BaseCommand

from assessments.tasks import abandon_inactive_attempts


class Command(BaseCommand):
    help = "Mark inactive in-progress assessment attempts abandoned."

    def handle(self, *args, **options):
        out = abandon_inactive_attempts()
        self.stdout.write(self.style.SUCCESS(str(out)))

