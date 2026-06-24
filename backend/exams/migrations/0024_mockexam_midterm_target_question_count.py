# Generated manually — midterm planner: target question count

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0023_pastpaperpack_practicetest_pastpaper_pack"),
    ]

    operations = [
        migrations.AddField(
            model_name="mockexam",
            name="midterm_target_question_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="0 = no fixed target. Otherwise planner cap for total questions across modules.",
            ),
        ),
    ]
