"""Migration A: make pastpaper sections standalone (additive + backfill, NO drops).

Adds section-level fields to ``PracticeTest`` and backfills them from the soon-to-be-removed
``PastpaperPack`` grouping. No columns or tables are dropped here — see Migration B
(``0048_drop_pastpaperpack``) for the destructive step. Splitting them guarantees a data copy
always precedes any drop, so no existing test data is lost.
"""

from django.db import migrations, models


def backfill_sections(apps, schema_editor):
    """Copy pack title / publish-state onto each pastpaper section."""
    PracticeTest = apps.get_model("exams", "PracticeTest")
    qs = PracticeTest.objects.filter(pastpaper_pack__isnull=False).select_related(
        "pastpaper_pack"
    )
    for pt in qs.iterator():
        pack = pt.pastpaper_pack
        if pack is None:
            continue
        changed = False
        if not pt.collection_name and (pack.title or "").strip():
            pt.collection_name = pack.title
            changed = True
        if pack.is_published and not pt.is_published:
            pt.is_published = True
            pt.published_at = pack.published_at
            changed = True
        # Pack metadata was historically synced to sections, but backfill anything blank.
        if not pt.practice_date and pack.practice_date:
            pt.practice_date = pack.practice_date
            changed = True
        if not pt.label and pack.label:
            pt.label = pack.label
            changed = True
        if changed:
            pt.save()


def backfill_class_assignments(apps, schema_editor):
    """Fold each classroom Assignment's pastpaper_pack into its section id list."""
    Assignment = apps.get_model("classes", "Assignment")
    PracticeTest = apps.get_model("exams", "PracticeTest")
    for ca in Assignment.objects.filter(pastpaper_pack__isnull=False).iterator():
        section_ids = list(
            PracticeTest.objects.filter(
                pastpaper_pack_id=ca.pastpaper_pack_id, mock_exam__isnull=True
            ).values_list("id", flat=True)
        )
        if not section_ids:
            continue
        existing = list(ca.practice_test_ids or [])
        merged = sorted({int(x) for x in existing} | set(section_ids))
        if merged != existing:
            ca.practice_test_ids = merged
            ca.save(update_fields=["practice_test_ids"])


def backfill_access_grants(apps, schema_editor):
    """Convert pastpaper_pack RESOURCE grants into per-section practice_test grants."""
    Grant = apps.get_model("access", "ResourceAccessGrant")
    PracticeTest = apps.get_model("exams", "PracticeTest")
    pack_grants = Grant.objects.filter(scope="RESOURCE", resource_type="pastpaper_pack")
    for g in pack_grants.iterator():
        section_ids = list(
            PracticeTest.objects.filter(pastpaper_pack_id=g.resource_id).values_list(
                "id", flat=True
            )
        )
        for sid in section_ids:
            if (
                g.status == "ACTIVE"
                and Grant.objects.filter(
                    user_id=g.user_id,
                    scope="RESOURCE",
                    resource_type="practice_test",
                    resource_id=sid,
                    classroom_id=g.classroom_id,
                    status="ACTIVE",
                ).exists()
            ):
                continue
            Grant.objects.create(
                user_id=g.user_id,
                scope="RESOURCE",
                resource_type="practice_test",
                resource_id=sid,
                classroom_id=g.classroom_id,
                source=g.source,
                status=g.status,
                granted_by_id=g.granted_by_id,
                expires_at=g.expires_at,
            )


def noop(apps, schema_editor):
    # Reverse: AddField reversal drops the new columns; the backfilled rows/values are
    # additive and harmless, so the data steps are intentionally non-reversible no-ops.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0046_question_bank_question_question_bank_version"),
        ("classes", "0023_classroom_description_classroommaterial"),
        ("access", "0011_resourceaccessgrant_accessgrantevent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="practicetest",
            name="collection_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Optional grouping label (formerly the pastpaper pack title). Lets "
                    "standalone sections be distinguished/grouped in admin, builder and "
                    "student lists."
                ),
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="practicetest",
            name="is_published",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "Only published sections are shown to students who don't have an "
                    "explicit assignment. Section-level replacement for the old pack "
                    "publish gate."
                ),
            ),
        ),
        migrations.AddField(
            model_name="practicetest",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_sections, noop),
        migrations.RunPython(backfill_class_assignments, noop),
        migrations.RunPython(backfill_access_grants, noop),
    ]
