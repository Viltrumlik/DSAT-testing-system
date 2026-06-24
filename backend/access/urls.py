from django.urls import path

from .views import (
    EngineGrantClassroomView,
    EngineGrantEventsView,
    EngineGrantExtendView,
    EngineGrantListView,
    EngineGrantResourceView,
    EngineGrantRevokeView,
    EngineGrantSubjectView,
    EngineResourceSearchView,
    EngineResourceTypesView,
    GrantAccessView,
)

urlpatterns = [
    # Legacy subject-grant endpoint (unchanged).
    path("grant/", GrantAccessView.as_view(), name="access_grant"),
    # Access engine admin API (Phase 2).
    path("grants/", EngineGrantListView.as_view(), name="access_grants_list"),
    path("grants/subject/", EngineGrantSubjectView.as_view(), name="access_grant_subject"),
    path("grants/resource/", EngineGrantResourceView.as_view(), name="access_grant_resource"),
    path("grants/classroom/", EngineGrantClassroomView.as_view(), name="access_grant_classroom"),
    path("grants/<int:grant_id>/revoke/", EngineGrantRevokeView.as_view(), name="access_grant_revoke"),
    path("grants/<int:grant_id>/extend/", EngineGrantExtendView.as_view(), name="access_grant_extend"),
    path("grants/<int:grant_id>/events/", EngineGrantEventsView.as_view(), name="access_grant_events"),
    path("resources/", EngineResourceSearchView.as_view(), name="access_resource_search"),
    path("resource-types/", EngineResourceTypesView.as_view(), name="access_resource_types"),
]
