from django.db import migrations, models


def _backfill_reviewed_status(apps, schema_editor):
    Submission = apps.get_model("classes", "Submission")
    # Any submission with a teacher review row should be REVIEWED.
    Submission.objects.filter(review__isnull=False).update(status="REVIEWED")


def _verify_submission_review_consistency(apps, schema_editor):
    """Fail migration if reviews exist without REVIEWED status (data integrity)."""
    Submission = apps.get_model("classes", "Submission")
    SubmissionReview = apps.get_model("classes", "SubmissionReview")
    bad = (
        SubmissionReview.objects.exclude(submission__status="REVIEWED")
        .values_list("id", flat=True)
        .count()
    )
    if bad:
        raise RuntimeError(
            f"Invariant failed: {bad} SubmissionReview row(s) without Submission.status=REVIEWED after backfill."
        )
    # Submissions marked REVIEWED must have a review row
    orphan = Submission.objects.filter(status="REVIEWED").filter(review__isnull=True).count()
    if orphan:
        raise RuntimeError(
            f"Invariant failed: {orphan} Submission(s) with status REVIEWED but no SubmissionReview row."
        )


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0010_submission_files_review_schedule"),
    ]

    operations = [
        migrations.AlterField(
            model_name="submission",
            name="status",
            field=models.CharField(
                choices=[("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("REVIEWED", "Reviewed")],
                db_index=True,
                default="DRAFT",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="submissionreview",
            name="reviewed_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.RunPython(_backfill_reviewed_status, _noop_reverse),
        migrations.RunPython(_verify_submission_review_consistency, _noop_reverse),
    ]
