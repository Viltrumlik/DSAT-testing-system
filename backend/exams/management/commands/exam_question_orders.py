from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from exams.question_integrity import audit_question_orders, repair_modules_with_duplicate_orders


class Command(BaseCommand):
    help = "Audit Question ordering per module; optionally dense-repair duplicate (module_id, order) keys."

    def add_arguments(self, parser):
        parser.add_argument(
            "--module-id",
            type=int,
            default=None,
            help="Restrict audit/gap reporting to questions in this module_id.",
        )
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Dense-reindex modules that still violate UNIQUE(module_id, order).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max modules to repair (repair mode only).",
        )
        parser.add_argument("--json", action="store_true", help="Machine-readable JSON only.")

    def handle(self, *args, **options):
        mids = ([int(options["module_id"])] if options["module_id"] else None)
        audit = audit_question_orders(module_ids=mids)

        out: dict = {"audit": audit, "repair": None}
        if options["repair"] and audit["duplicate_pairs"]:
            repaired = repair_modules_with_duplicate_orders(limit=options["limit"])
            out["repair"] = {"modules_dense_reindexed": repaired}
        elif options["repair"]:
            out["repair"] = {"modules_dense_reindexed": []}

        if options["json"]:
            self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
            return

        self.stdout.write("EXAM QUESTION ORDER INTEGRITY")
        self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
