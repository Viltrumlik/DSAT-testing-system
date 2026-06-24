from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0031_attempt_idempotency_keys"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="module",
            constraint=models.UniqueConstraint(
                fields=("practice_test", "module_order"),
                name="uniq_module_order_per_test",
            ),
        ),
        migrations.AddConstraint(
            model_name="module",
            constraint=models.CheckConstraint(
                condition=Q(module_order__in=[1, 2]),
                name="chk_module_order_1_2",
            ),
        ),
        migrations.AddConstraint(
            model_name="module",
            constraint=models.CheckConstraint(
                condition=Q(time_limit_minutes__gt=0),
                name="chk_module_time_limit_positive",
            ),
        ),
    ]

