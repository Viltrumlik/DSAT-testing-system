from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0008_unique_homework_per_classroom_set"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentanswer",
            name="client_seq",
            field=models.BigIntegerField(db_index=True, default=0),
        ),
    ]

