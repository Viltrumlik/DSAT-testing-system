from django.db import migrations


def delete_mock_sat_shells(apps, schema_editor):
    """
    Remove timed SAT mock shells from the student mock list.
    Section PracticeTests are detached (mock_exam=NULL) so they stay in the pastpaper library;
    portal rows and MockExam rows are removed. Midterms (kind=MIDTERM) are untouched.
    """
    MockExam = apps.get_model("exams", "MockExam")
    PracticeTest = apps.get_model("exams", "PracticeTest")
    PortalMockExam = apps.get_model("exams", "PortalMockExam")

    mock_qs = MockExam.objects.filter(kind="MOCK_SAT")
    mock_ids = list(mock_qs.values_list("pk", flat=True))
    if not mock_ids:
        return

    PracticeTest.objects.filter(mock_exam_id__in=mock_ids).update(mock_exam_id=None)
    PortalMockExam.objects.filter(mock_exam_id__in=mock_ids).delete()
    mock_qs.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0020_clarify_practice_vs_mock_help_text"),
    ]

    operations = [
        migrations.RunPython(delete_mock_sat_shells, noop_reverse),
    ]
