from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0017_detach_practice_tests_from_mocks"),
    ]

    operations = [
        migrations.AddField(
            model_name="practicetest",
            name="title",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Pastpaper / practice test name (shown in admin and student lists).",
                max_length=255,
            ),
        ),
    ]
