from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0011_question_option_a_image_question_option_b_image_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="option_a",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="question",
            name="option_b",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="question",
            name="option_c",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="question",
            name="option_d",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="question",
            name="correct_answers",
            field=models.TextField(
                help_text="For math input, separate multiple correct answers with a comma. e.g. '2/3, 0.666, 0.667'"
            ),
        ),
    ]
