from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from realtime.models import RealtimeEvent


class Command(BaseCommand):
    help = "Delete realtime outbox events older than N hours (default 24h)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--limit", type=int, default=50000)

    def handle(self, *args, **options):
        hours = int(options["hours"])
        limit = int(options["limit"])
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        ids = list(
            RealtimeEvent.objects.filter(created_at__lt=cutoff)
            .order_by("id")
            .values_list("id", flat=True)[:limit]
        )
        if not ids:
            self.stdout.write("No realtime events to delete.")
            return
        deleted, _ = RealtimeEvent.objects.filter(id__in=ids).delete()
        self.stdout.write(f"Deleted {deleted} realtime events older than {hours}h (limit {limit}).")

