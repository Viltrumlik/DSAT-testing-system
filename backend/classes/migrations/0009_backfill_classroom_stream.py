from django.db import migrations


def forwards(apps, schema_editor):
    ClassroomStreamItem = apps.get_model("classes", "ClassroomStreamItem")
    ClassPost = apps.get_model("classes", "ClassPost")
    Assignment = apps.get_model("classes", "Assignment")
    Submission = apps.get_model("classes", "Submission")

    for p in ClassPost.objects.all().iterator():
        ClassroomStreamItem.objects.get_or_create(
            stream_type="post",
            related_id=p.pk,
            defaults={"classroom_id": p.classroom_id, "actor_id": p.author_id},
        )
    for a in Assignment.objects.all().iterator():
        ClassroomStreamItem.objects.get_or_create(
            stream_type="assignment",
            related_id=a.pk,
            defaults={"classroom_id": a.classroom_id, "actor_id": a.created_by_id},
        )
    for s in Submission.objects.filter(status="SUBMITTED").select_related("assignment").iterator():
        ClassroomStreamItem.objects.get_or_create(
            stream_type="submission",
            related_id=s.pk,
            defaults={
                "classroom_id": s.assignment.classroom_id,
                "actor_id": s.student_id,
            },
        )


def backwards(apps, schema_editor):
    ClassroomStreamItem = apps.get_model("classes", "ClassroomStreamItem")
    ClassroomStreamItem.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0008_classroom_stream_comments"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
