from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0032_module_integrity_constraints"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="testattempt",
            constraint=models.UniqueConstraint(
                fields=["student", "practice_test"],
                condition=Q(is_completed=False) & ~Q(current_state="ABANDONED"),
                name="uniq_active_attempt_per_student_test",
            ),
        ),
    ]

