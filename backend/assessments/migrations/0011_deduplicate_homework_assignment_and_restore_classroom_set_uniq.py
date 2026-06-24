# Generated manually for assessment homework uniqueness

from django.db import migrations, models
from django.db.models import Count


def dedupe_homework_assignments_then_prepare(apps, schema_editor):
    """
    Before adding UNIQUE(classroom_id, assessment_set_id), remove duplicate homework rows.

    Keeper: earliest ``HomeworkAssignment.id`` per (classroom, assessment_set).
    Losers: delete linked ``classes.Assignment`` rows (cascade removes losers' homework rows).
    """
    HomeworkAssignment = apps.get_model("assessments", "HomeworkAssignment")
    Assignment = apps.get_model("classes", "Assignment")

    dup_pairs = (
        HomeworkAssignment.objects.values("classroom_id", "assessment_set_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for pair in dup_pairs:
        cid = pair["classroom_id"]
        sid = pair["assessment_set_id"]
        rows = list(
            HomeworkAssignment.objects.filter(classroom_id=cid, assessment_set_id=sid).order_by("id")
        )
        for loser_hw in rows[1:]:
            aid = loser_hw.assignment_id
            if aid:
                Assignment.objects.filter(pk=aid).delete()


def noop_reverse_de_dupe(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0010_remove_homeworkassignment_uniq_assessment_hw_classroom_set_and_more"),
    ]

    operations = [
        migrations.RunPython(dedupe_homework_assignments_then_prepare, noop_reverse_de_dupe),
        migrations.AddConstraint(
            model_name="homeworkassignment",
            constraint=models.UniqueConstraint(
                fields=["classroom", "assessment_set"],
                name="uniq_assessment_hw_classroom_set",
            ),
        ),
    ]
