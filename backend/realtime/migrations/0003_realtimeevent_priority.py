from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("realtime", "0002_realtimeevent_dedupe_and_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="realtimeevent",
            name="priority",
            field=models.CharField(
                choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")],
                db_index=True,
                default="medium",
                max_length=16,
            ),
        ),
    ]
