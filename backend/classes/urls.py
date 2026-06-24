from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ClassroomViewSet,
    JoinClassView,
    ClassPostViewSet,
    AssignmentViewSet,
    SubmissionAdminViewSet,
    ClassCommentListCreateView,
    OpsStatsView,
    OpsAttentionView,
)
from .views_rankings import RankingsView, RankingRecomputeView, RankingConfigView, RankingHistoryView
from .views_attendance import (
    AttendanceSessionsView,
    AttendanceSessionDetailView,
    AttendanceMarkView,
    AttendanceMarkAllPresentView,
    AttendanceFinalizeView,
    AttendanceSummaryView,
    AttendanceMeView,
    AttendanceStudentView,
)
from .views_analytics import AnalyticsClassView, AnalyticsMeView, AnalyticsStudentView
from .views_gradebook import GradebookOverviewView, GradebookAssignmentView
from .views_materials import ClassroomMaterialsView, ClassroomMaterialDetailView
from .views_assign import AssignMidtermView, AssignTeacherView, TransferOwnershipView, ClassroomGovernanceDeleteView
from .views_results import ClassroomMidtermResultsView, ClassroomUnifiedResultsView
from .views_roster import MemberManageView


router = DefaultRouter()
router.register(r"", ClassroomViewSet, basename="classroom")

posts_router = DefaultRouter()
posts_router.register(r"", ClassPostViewSet, basename="class-posts")

assignments_router = DefaultRouter()
assignments_router.register(r"", AssignmentViewSet, basename="class-assignments")

submissions_router = DefaultRouter()
submissions_router.register(r"", SubmissionAdminViewSet, basename="class-submissions")


urlpatterns = [
    path("join/", JoinClassView.as_view(), name="class-join"),
    path("ops/stats/", OpsStatsView.as_view(), name="class-ops-stats"),
    path("ops/attention/", OpsAttentionView.as_view(), name="class-ops-attention"),
    path("<int:classroom_pk>/comments/", ClassCommentListCreateView.as_view(), name="class-comments"),
    path("<int:classroom_pk>/members/<int:user_id>/", MemberManageView.as_view(), name="class-member-manage"),
    path("<int:classroom_pk>/rankings/recompute/", RankingRecomputeView.as_view(), name="class-rankings-recompute"),
    path("<int:classroom_pk>/rankings/config/", RankingConfigView.as_view(), name="class-rankings-config"),
    path("<int:classroom_pk>/rankings/<str:kind>/history/", RankingHistoryView.as_view(), name="class-rankings-history"),
    path("<int:classroom_pk>/rankings/<str:kind>/", RankingsView.as_view(), name="class-rankings"),
    # Attendance
    path("<int:classroom_pk>/attendance/sessions/", AttendanceSessionsView.as_view(), name="attendance-sessions"),
    path("<int:classroom_pk>/attendance/sessions/<int:session_id>/", AttendanceSessionDetailView.as_view(), name="attendance-session-detail"),
    path("<int:classroom_pk>/attendance/sessions/<int:session_id>/mark/", AttendanceMarkView.as_view(), name="attendance-mark"),
    path("<int:classroom_pk>/attendance/sessions/<int:session_id>/mark-all-present/", AttendanceMarkAllPresentView.as_view(), name="attendance-mark-all-present"),
    path("<int:classroom_pk>/attendance/sessions/<int:session_id>/finalize/", AttendanceFinalizeView.as_view(), name="attendance-finalize"),
    path("<int:classroom_pk>/attendance/summary/", AttendanceSummaryView.as_view(), name="attendance-summary"),
    path("<int:classroom_pk>/attendance/me/", AttendanceMeView.as_view(), name="attendance-me"),
    path("<int:classroom_pk>/attendance/students/<int:student_id>/", AttendanceStudentView.as_view(), name="attendance-student"),
    # Analytics
    path("<int:classroom_pk>/analytics/class/", AnalyticsClassView.as_view(), name="analytics-class"),
    path("<int:classroom_pk>/analytics/me/", AnalyticsMeView.as_view(), name="analytics-me"),
    path("<int:classroom_pk>/analytics/students/<int:student_id>/", AnalyticsStudentView.as_view(), name="analytics-student"),
    # Teacher assignment + admin governance
    path("<int:classroom_pk>/assign-midterm/", AssignMidtermView.as_view(), name="class-assign-midterm"),
    path("<int:classroom_pk>/assign-teacher/", AssignTeacherView.as_view(), name="class-assign-teacher"),
    path("<int:classroom_pk>/transfer-ownership/", TransferOwnershipView.as_view(), name="class-transfer-ownership"),
    path("<int:classroom_pk>/governance-delete/", ClassroomGovernanceDeleteView.as_view(), name="class-governance-delete"),
    # Classroom materials (downloadable PDF/DOCX)
    path("<int:classroom_pk>/materials/", ClassroomMaterialsView.as_view(), name="class-materials"),
    path("<int:classroom_pk>/materials/<int:material_id>/", ClassroomMaterialDetailView.as_view(), name="class-material-detail"),
    # Teacher gradebook
    path("<int:classroom_pk>/midterm-results/", ClassroomMidtermResultsView.as_view(), name="class-midterm-results"),
    path("<int:classroom_pk>/results/", ClassroomUnifiedResultsView.as_view(), name="class-unified-results"),
    path("<int:classroom_pk>/gradebook/", GradebookOverviewView.as_view(), name="gradebook-overview"),
    path("<int:classroom_pk>/gradebook/assignments/<int:assignment_id>/", GradebookAssignmentView.as_view(), name="gradebook-assignment"),
    path("submissions/", include(submissions_router.urls)),
    path("<int:classroom_pk>/posts/", include(posts_router.urls)),
    path("<int:classroom_pk>/assignments/", include(assignments_router.urls)),
    path("", include(router.urls)),
]

