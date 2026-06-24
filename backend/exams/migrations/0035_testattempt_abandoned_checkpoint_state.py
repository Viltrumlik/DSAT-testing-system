from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0034_remove_testattempt_uniq_active_attempt_per_student_test_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="abandoned_checkpoint_state",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Snapshot of exam engine current_state persisted when marking this row ABANDONED; drives resume."
                ),
                max_length=24,
                null=True,
            ),
        ),
    ]
