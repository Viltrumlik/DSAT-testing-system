from django.db import migrations


def detach_mock_sat_then_remove_shells(apps, schema_editor):
    """
    Idempotent safety net: same semantics as 0021 after we fixed CASCADE loss.
    Detach PracticeTests from MOCK_SAT, remove portal rows and mock shells. Midterms stay.
    No-op if no MOCK_SAT rows (e.g. already cleaned by updated 0021).
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
        ("exams", "0021_remove_all_mock_sat_exams"),
    ]

    operations = [
        migrations.RunPython(detach_mock_sat_then_remove_shells, noop_reverse),
    ]
