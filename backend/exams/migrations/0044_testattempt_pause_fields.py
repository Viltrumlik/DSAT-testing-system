# Manually generated to track pause-related state.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0043_practicetestpack_practicetest_practice_test_pack'),
    ]

    operations = [
        migrations.AddField(
            model_name='testattempt',
            name='module_1_paused_seconds',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='testattempt',
            name='module_2_paused_seconds',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='testattempt',
            name='pause_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
