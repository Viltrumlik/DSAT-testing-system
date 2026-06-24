from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0014_governance_events_and_lineage"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentquestion",
            name="explanation",
            field=models.TextField(blank=True, default=""),
        ),
    ]
