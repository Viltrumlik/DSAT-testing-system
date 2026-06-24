from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand

from exams.models import PracticeTest


_SUBJECT_TAIL_RE = re.compile(
    r"(?:\s*[—–-]\s*(Reading\s*&\s*Writing|R\s*&\s*W|English|Math|Mathematics)\s*)+$",
    re.IGNORECASE,
)


def _suspicious_title_reasons(title: str) -> list[str]:
    t = (title or "").strip()
    if not t:
        return []
    out: list[str] = []
    if "//" in t or "\\\\" in t:
        out.append("contains_double_slash")
    if "  " in t:
        out.append("contains_double_space")
    # subject tail repeated (e.g. "X — Math — Math")
    if _SUBJECT_TAIL_RE.search(t):
        base = _SUBJECT_TAIL_RE.sub("", t).strip()
        if base and _SUBJECT_TAIL_RE.search(base):
            out.append("repeated_subject_tail")
    # overly long titles tend to be concatenation bugs
    if len(t) > 180:
        out.append("very_long_title")
    return out


class Command(BaseCommand):
    help = "Read-only integrity audit for standalone practice/pastpaper sections (prints counts + sample IDs)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Max IDs to print per category.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")

    def handle(self, *args, **options):
        limit = int(options["limit"] or 50)
        as_json = bool(options["json"])

        report: dict[str, dict] = {}

        # ── Sections (PracticeTest) ─────────────────────────────────────────
        # Standalone pastpaper/practice sections (no mock, no practice-test pack).
        standalone_ids = list(
            PracticeTest.objects.filter(
                mock_exam__isnull=True, practice_test_pack__isnull=True
            ).values_list("id", flat=True)[:limit]
        )

        # Suspicious titles (likely concatenation/corruption artifacts).
        suspicious_title_rows = []
        for pt in PracticeTest.objects.only("id", "title").order_by("id").iterator(chunk_size=500):
            reasons = _suspicious_title_reasons(pt.title or "")
            if not reasons:
                continue
            suspicious_title_rows.append({"practice_test_id": pt.pk, "reasons": reasons, "title": (pt.title or "")[:220]})
            if len(suspicious_title_rows) >= limit:
                break

        report["sections"] = {
            "standalone_sections": {
                "count": PracticeTest.objects.filter(
                    mock_exam__isnull=True, practice_test_pack__isnull=True
                ).count(),
                "ids": standalone_ids,
            },
            "sections_with_suspicious_titles": {
                "count": len(suspicious_title_rows),
                "rows": suspicious_title_rows,
            },
        }

        if as_json:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write("TEST LIBRARY INTEGRITY AUDIT")
        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
