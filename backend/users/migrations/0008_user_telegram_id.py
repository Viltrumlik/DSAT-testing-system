import re

from django.db import migrations, models


def backfill_telegram_id(apps, schema_editor):
    User = apps.get_model("users", "User")
    for u in User.objects.all().only("id", "email", "telegram_id"):
        if u.telegram_id is not None:
            continue
        m = re.match(r"^tg(\d+)@", (u.email or ""), re.IGNORECASE)
        if m:
            User.objects.filter(pk=u.pk).update(telegram_id=int(m.group(1)))


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_user_phone_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="telegram_id",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                help_text="Telegram user id when linked or signed up via Telegram.",
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(backfill_telegram_id, migrations.RunPython.noop),
    ]
