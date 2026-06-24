from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0006_security_alert"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assessmentset",
            name="category",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
    ]
