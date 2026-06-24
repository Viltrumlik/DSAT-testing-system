from django.db import migrations, models


def backfill_question_order_high_water(apps, schema_editor):
    Module = apps.get_model("exams", "Module")
    Question = apps.get_model("exams", "Question")
    from django.db.models import Max

    for pk in Module.objects.values_list("id", flat=True).iterator(chunk_size=500):
        m = Question.objects.filter(module_id=pk).aggregate(m=Max("order"))["m"]
        hv = int(m) if m is not None else 0
        Module.objects.filter(pk=pk).update(question_order_high_water=hv)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0038_practicetest_pastpaper_detach_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="module",
            name="question_order_high_water",
            field=models.BigIntegerField(
                default=0,
                help_text="Monotonic high-water mark for Question.order allocations (avoids Max(order) hotspot).",
            ),
        ),
        migrations.RunPython(backfill_question_order_high_water, migrations.RunPython.noop),
    ]
