from django.db import migrations, models
from django.db.models import Count, Q


def normalize_question_orders(apps, schema_editor):
    Question = apps.get_model("exams", "Question")
    module_ids = (
        Question.objects.exclude(module_id__isnull=True)
        .values_list("module_id", flat=True)
        .distinct()
    )
    for mid in module_ids:
        rows = list(Question.objects.filter(module_id=mid).order_by("order", "id"))
        for idx, row in enumerate(rows):
            if row.order != idx:
                Question.objects.filter(pk=row.pk).update(order=idx)


def dedupe_pastpaper_pack_subject(apps, schema_editor):
    """
    At most one PracticeTest per (pastpaper_pack, subject) may stay linked to the pack.
    Duplicates (higher ``id``) are detached: ``pastpaper_pack_id`` set to NULL (standalone section).
    """
    PracticeTest = apps.get_model("exams", "PracticeTest")
    dup_groups = (
        PracticeTest.objects.exclude(pastpaper_pack_id__isnull=True)
        .values("pastpaper_pack_id", "subject")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
    )
    for g in dup_groups:
        pack_id = g["pastpaper_pack_id"]
        subject = g["subject"]
        rows = list(
            PracticeTest.objects.filter(
                pastpaper_pack_id=pack_id, subject=subject
            ).order_by("id")
        )
        if len(rows) <= 1:
            continue
        keeper_id = rows[0].pk
        dup_ids = [r.pk for r in rows[1:]]
        PracticeTest.objects.filter(pk__in=dup_ids).update(pastpaper_pack_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0036_attempt_engine_audit"),
    ]

    operations = [
        migrations.RunPython(
            normalize_question_orders,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            dedupe_pastpaper_pack_subject,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="question",
            constraint=models.UniqueConstraint(
                fields=["module", "order"],
                condition=Q(module__isnull=False),
                name="uniq_question_order_per_module",
            ),
        ),
        migrations.AddConstraint(
            model_name="practicetest",
            constraint=models.UniqueConstraint(
                fields=["pastpaper_pack", "subject"],
                condition=Q(pastpaper_pack__isnull=False),
                name="uniq_pastpaper_pack_subject",
            ),
        ),
    ]
