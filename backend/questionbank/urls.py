"""Question Bank admin API routes (read-only, Phase A). Mounted at api/questionbank/."""
from django.urls import path

from . import views

app_name = "questionbank"

urlpatterns = [
    # Read-only (Phase A)
    path("questions/", views.BankQuestionListView.as_view(), name="question-list"),
    # Bulk + write actions must precede <int:pk> (they don't collide, but keep grouped).
    path("questions/bulk/", views.BankQuestionBulkView.as_view(), name="question-bulk"),
    path("questions/<int:pk>/", views.BankQuestionDetailView.as_view(), name="question-detail"),
    path("questions/<int:pk>/archive/", views.BankQuestionArchiveView.as_view(), name="question-archive"),
    path("questions/<int:pk>/restore/", views.BankQuestionRestoreView.as_view(), name="question-restore"),
    path("questions/<int:pk>/classify/", views.BankQuestionClassifyView.as_view(), name="question-classify"),
    path("questions/<int:pk>/approve/", views.BankQuestionApproveView.as_view(), name="question-approve"),
    path("questions/<int:pk>/reject/", views.BankQuestionRejectView.as_view(), name="question-reject"),
    path("questions/<int:pk>/accept-suggestion/", views.BankQuestionAcceptSuggestionView.as_view(), name="question-accept-suggestion"),
    path("passages/", views.BankPassageListView.as_view(), name="passage-list"),
    path("passages/<int:pk>/", views.BankPassageDetailView.as_view(), name="passage-detail"),
    path("versions/", views.BankQuestionVersionListView.as_view(), name="version-list"),
    path("domains/", views.BankDomainListView.as_view(), name="domain-list"),
    path("skills/", views.BankSkillListView.as_view(), name="skill-list"),
    # Student practice (M9) — APPROVED-only, no answer leak
    path("practice/", views.PracticeQuestionListView.as_view(), name="practice-list"),
    path("practice/taxonomy/", views.PracticeTaxonomyView.as_view(), name="practice-taxonomy"),
    path("practice/<int:pk>/", views.PracticeQuestionDetailView.as_view(), name="practice-detail"),
    path("practice/<int:pk>/answer/", views.PracticeAnswerView.as_view(), name="practice-answer"),
    # Import batch management (Phase B + M5 upload)
    path("import-batches/", views.ImportBatchListView.as_view(), name="batch-list"),
    path("import-batches/upload/", views.ImportBatchUploadView.as_view(), name="batch-upload"),
    path("import-batches/<int:pk>/", views.ImportBatchDetailView.as_view(), name="batch-detail"),
    path("import-batches/<int:batch_id>/candidates/", views.ImportCandidateListView.as_view(), name="batch-candidates"),
    path("import-batches/<int:pk>/promote/", views.ImportBatchPromoteView.as_view(), name="batch-promote"),
    path("import-candidates/<int:pk>/", views.ImportCandidateDetailView.as_view(), name="candidate-detail"),
]
