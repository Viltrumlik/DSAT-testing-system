from django.core.management.base import BaseCommand

from classes.stale_storage_cleanup import run_stale_storage_cleanup


class Command(BaseCommand):
    help = "Retry failed homework file deletions recorded in StaleStorageBlob (cron-friendly)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)

    def handle(self, *args, **options):
        stats = run_stale_storage_cleanup(batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(str(stats)))
