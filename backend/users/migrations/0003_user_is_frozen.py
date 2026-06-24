from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_frozen",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
