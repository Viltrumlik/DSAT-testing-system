from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Repair pastpaper library integrity issues. Pastpaper packs were removed in favour of "
        "standalone sections, so there is no longer any pack/section signature to normalize; "
        "this command is now a no-op kept for ops compatibility."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be changed.")
        parser.add_argument("--limit", type=int, default=2000, help="Unused (kept for compatibility).")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary.")

    def handle(self, *args, **options):
        out: dict = {}
        if options.get("json"):
            self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
            return
        self.stdout.write("TEST LIBRARY INTEGRITY REPAIR")
        self.stdout.write("Nothing to repair: pastpaper packs were removed (sections are standalone).")
