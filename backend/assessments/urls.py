from django.urls import path

from .views import (
    AdminAssessmentSetListCreateView,
    AdminAssessmentSetDetailView,
    AdminPublishAssessmentSetView,
    AdminValidatePublishView,
    AdminAssessmentSetVersionListView,
    AdminAssessmentQuestionCreateView,
    AdminAssessmentQuestionDetailView,
    AdminQuestionBankSelectView,
    AdminQuestionBankTaxonomyView,
    AdminAssessmentQuestionFromBankView,
    AssignAssessmentHomeworkView,
    StartAttemptView,
    AttemptBundleView,
    AttemptPedagogicalReviewView,
    AttemptTeacherFeedbackView,
    TeacherSubmissionQueueView,
    SaveAnswerView,
    SubmitAttemptView,
    AbandonAttemptView,
    MyAssessmentResultForAssignmentView,
    AdminGradingMetricsView,
    AdminGradingPrometheusMetricsView,
    AdminHomeworkPrometheusMetricsView,
    AdminBuilderTelemetryView,
    AdminAttemptStatusView,
    AdminRequeueAttemptView,
    AdminForceGradeAttemptView,
    AdminGovernanceEventListView,
    AdminFailedAttemptsListView,
)


urlpatterns = [
    # Admin authoring
    path("admin/sets/", AdminAssessmentSetListCreateView.as_view(), name="assessment-admin-sets"),
    path("admin/sets/<int:pk>/", AdminAssessmentSetDetailView.as_view(), name="assessment-admin-set-detail"),
    path("admin/sets/<int:pk>/publish/", AdminPublishAssessmentSetView.as_view(), name="assessment-admin-set-publish"),
    path("admin/sets/<int:pk>/validate-publish/", AdminValidatePublishView.as_view(), name="assessment-admin-set-validate-publish"),
    path("admin/sets/<int:pk>/versions/", AdminAssessmentSetVersionListView.as_view(), name="assessment-admin-set-versions"),
    path("admin/sets/<int:set_pk>/questions/", AdminAssessmentQuestionCreateView.as_view(), name="assessment-admin-question-create"),
    path("admin/sets/<int:set_pk>/questions/from-bank/", AdminAssessmentQuestionFromBankView.as_view(), name="assessment-admin-question-from-bank"),
    path("admin/questions/<int:pk>/", AdminAssessmentQuestionDetailView.as_view(), name="assessment-admin-question-detail"),
    # M4 — Question Bank picker (APPROVED-only) for the assessment builder
    path("admin/question-bank/select/", AdminQuestionBankSelectView.as_view(), name="assessment-admin-qb-select"),
    path("admin/question-bank/taxonomy/", AdminQuestionBankTaxonomyView.as_view(), name="assessment-admin-qb-taxonomy"),
    # Admin grading controls / metrics
    path("admin/grading/metrics/", AdminGradingMetricsView.as_view(), name="assessment-admin-grading-metrics"),
    path(
        "admin/grading/metrics/prometheus/",
        AdminGradingPrometheusMetricsView.as_view(),
        name="assessment-admin-grading-metrics-prometheus",
    ),
    path(
        "admin/homework/metrics/prometheus/",
        AdminHomeworkPrometheusMetricsView.as_view(),
        name="assessment-admin-homework-metrics-prometheus",
    ),
    path(
        "admin/builder/telemetry/",
        AdminBuilderTelemetryView.as_view(),
        name="assessment-admin-builder-telemetry",
    ),
    path("admin/attempts/<int:attempt_id>/", AdminAttemptStatusView.as_view(), name="assessment-admin-attempt-status"),
    path("admin/attempts/<int:attempt_id>/requeue/", AdminRequeueAttemptView.as_view(), name="assessment-admin-attempt-requeue"),
    path("admin/attempts/<int:attempt_id>/force-grade/", AdminForceGradeAttemptView.as_view(), name="assessment-admin-attempt-force-grade"),
    path("admin/attempts/failed/", AdminFailedAttemptsListView.as_view(), name="assessment-admin-attempts-failed"),
    # Ops audit log
    path("admin/governance-events/", AdminGovernanceEventListView.as_view(), name="assessment-admin-governance-events"),
    # Teacher assign
    path("homework/assign/", AssignAssessmentHomeworkView.as_view(), name="assessment-homework-assign"),
    # Student attempt flow
    path("attempts/start/", StartAttemptView.as_view(), name="assessment-attempt-start"),
    path("attempts/<int:attempt_id>/bundle/", AttemptBundleView.as_view(), name="assessment-attempt-bundle"),
    path("attempts/<int:attempt_id>/review/", AttemptPedagogicalReviewView.as_view(), name="assessment-attempt-pedagogical-review"),
    path("attempts/<int:attempt_id>/feedback/", AttemptTeacherFeedbackView.as_view(), name="assessment-attempt-feedback"),
    # Teacher submission queue (all classrooms where user is teacher)
    path("teacher/submission-queue/", TeacherSubmissionQueueView.as_view(), name="assessment-teacher-submission-queue"),
    path("attempts/answer/", SaveAnswerView.as_view(), name="assessment-attempt-answer"),
    path("attempts/submit/", SubmitAttemptView.as_view(), name="assessment-attempt-submit"),
    path("attempts/abandon/", AbandonAttemptView.as_view(), name="assessment-attempt-abandon"),
    # Student result (by assignment id)
    path("homework/<int:assignment_id>/my-result/", MyAssessmentResultForAssignmentView.as_view(), name="assessment-homework-my-result"),
]

