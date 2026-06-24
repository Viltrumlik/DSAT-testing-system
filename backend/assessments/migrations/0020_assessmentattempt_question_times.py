# Manually generated to add per-question time tracking.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0019_add_attempt_feedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessmentattempt',
            name='question_times',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
