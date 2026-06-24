# Generated manually for mock / midterm exam kinds

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0012_expand_question_option_lengths"),
    ]

    operations = [
        migrations.AddField(
            model_name="mockexam",
            name="kind",
            field=models.CharField(
                choices=[
                    ("MOCK_SAT", "Full SAT mock (Reading & Writing + Math)"),
                    ("MIDTERM", "Midterm (custom time, 1–2 modules, one subject)"),
                ],
                db_index=True,
                default="MOCK_SAT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mockexam",
            name="midterm_module1_minutes",
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name="mockexam",
            name="midterm_module2_minutes",
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name="mockexam",
            name="midterm_module_count",
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name="mockexam",
            name="midterm_subject",
            field=models.CharField(
                choices=[("READING_WRITING", "Reading & Writing"), ("MATH", "Math")],
                default="READING_WRITING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="practicetest",
            name="skip_default_modules",
            field=models.BooleanField(
                default=False,
                help_text="If True, post_save does not auto-create SAT modules (midterm/custom builds).",
            ),
        ),
    ]
