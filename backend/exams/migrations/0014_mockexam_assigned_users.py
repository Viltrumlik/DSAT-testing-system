# Generated manually for LMS: mock exams assignable separately from practice tests.

from django.conf import settings
from django.db import migrations, models


def copy_assigned_users_to_mock_exams(apps, schema_editor):
    MockExam = apps.get_model("exams", "MockExam")
    PracticeTest = apps.get_model("exams", "PracticeTest")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    for exam in MockExam.objects.all():
        ids = set()
        for pt in PracticeTest.objects.filter(mock_exam_id=exam.id):
            ids.update(pt.assigned_users.values_list("id", flat=True))
        if ids:
            exam.assigned_users.set(User.objects.filter(pk__in=ids))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0013_mockexam_kind_midterm_practicetest_skip_modules"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="mockexam",
            name="assigned_users",
            field=models.ManyToManyField(
                blank=True,
                help_text="Students/teachers who see this mock on the Mock Exam page.",
                related_name="assigned_mock_exams",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copy_assigned_users_to_mock_exams, noop_reverse),
    ]
