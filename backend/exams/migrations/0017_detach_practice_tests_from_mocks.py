from django.db import migrations, models


def detach_practice_from_mocks(apps, schema_editor):
    PracticeTest = apps.get_model("exams", "PracticeTest")
    PracticeTest.objects.exclude(mock_exam_id=None).update(mock_exam_id=None)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0016_mockexam_is_published"),
    ]

    operations = [
        migrations.RunPython(detach_practice_from_mocks, noop_reverse),
        migrations.AlterField(
            model_name="mockexam",
            name="is_published",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="When True, students with portal access see this mock; section tests are not listed under Practice Tests.",
            ),
        ),
    ]
