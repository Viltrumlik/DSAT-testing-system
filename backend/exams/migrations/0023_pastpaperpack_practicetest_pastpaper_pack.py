import django.db.models.deletion
from django.db import migrations, models


def backfill_pastpaper_packs(apps, schema_editor):
    PracticeTest = apps.get_model("exams", "PracticeTest")
    PastpaperPack = apps.get_model("exams", "PastpaperPack")

    groups = {}
    for pt in PracticeTest.objects.filter(mock_exam__isnull=True, pastpaper_pack__isnull=True):
        key = (
            pt.practice_date,
            pt.form_type,
            (pt.label or "").strip(),
        )
        groups.setdefault(key, []).append(pt.pk)

    for key, pks in groups.items():
        if len(pks) < 2:
            continue
        practice_date, form_type, label = key
        pack = PastpaperPack.objects.create(
            title="",
            practice_date=practice_date,
            form_type=form_type or "INTERNATIONAL",
            label=label,
        )
        PracticeTest.objects.filter(pk__in=pks).update(pastpaper_pack_id=pack.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0022_detach_mock_sat_sections_before_removing_mocks"),
    ]

    operations = [
        migrations.CreateModel(
            name="PastpaperPack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, default="", help_text="Pack title shown on student practice cards.", max_length=255)),
                ("practice_date", models.DateField(blank=True, db_index=True, null=True)),
                ("label", models.CharField(blank=True, help_text="e.g. A, B — shared by sections in this pack.", max_length=10)),
                (
                    "form_type",
                    models.CharField(
                        choices=[("INTERNATIONAL", "International Form"), ("US", "US Form")],
                        db_index=True,
                        default="INTERNATIONAL",
                        max_length=20,
                    ),
                ),
            ],
            options={
                "db_table": "pastpaper_packs",
                "ordering": ["-practice_date", "-created_at"],
            },
        ),
        migrations.AddField(
            model_name="practicetest",
            name="pastpaper_pack",
            field=models.ForeignKey(
                blank=True,
                help_text="When set (and mock_exam is NULL), this section belongs to a grouped pastpaper card.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sections",
                to="exams.pastpaperpack",
            ),
        ),
        migrations.RunPython(backfill_pastpaper_packs, noop_reverse),
    ]
