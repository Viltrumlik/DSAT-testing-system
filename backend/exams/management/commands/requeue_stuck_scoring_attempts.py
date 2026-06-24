from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from exams.models import TestAttempt
from exams.tasks import score_attempt_async


class Command(BaseCommand):
    help = "Re-enqueue scoring for attempts stuck in SCORING older than N minutes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=10,
            help="Only requeue attempts with scoring_started_at older than this many minutes.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum attempts to requeue per run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would be requeued.",
        )

    def handle(self, *args, **options):
        older = int(options["older_than_minutes"] or 10)
        limit = int(options["limit"] or 500)
        dry = bool(options["dry_run"])

        cutoff = timezone.now() - timezone.timedelta(minutes=older)
        qs = (
            TestAttempt.objects.filter(
                current_state=TestAttempt.STATE_SCORING,
                is_completed=False,
                scoring_started_at__isnull=False,
                scoring_started_at__lte=cutoff,
            )
            .order_by("scoring_started_at")[:limit]
        )

        count = 0
        for att in qs:
            count += 1
            if dry:
                self.stdout.write(f"would_requeue attempt_id={att.pk} scoring_started_at={att.scoring_started_at}")
                continue
            score_attempt_async.delay(att.pk)
            self.stdout.write(f"requeued attempt_id={att.pk}")

        self.stdout.write(f"done requeued_count={count} dry_run={dry}")

