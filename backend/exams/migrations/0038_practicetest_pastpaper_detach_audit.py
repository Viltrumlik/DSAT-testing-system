from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0037_question_and_pastpaper_invariants"),
    ]

    operations = [
        migrations.AddField(
            model_name="practicetest",
            name="pastpaper_detached_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text="Set when this section is removed from a pastpaper pack (audit / drift detection).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="practicetest",
            name="pastpaper_detached_pack_id",
            field=models.PositiveIntegerField(
                blank=True,
                editable=False,
                help_text="Snapshot of pastpaper_pack_id at detach time.",
                null=True,
            ),
        ),
    ]
