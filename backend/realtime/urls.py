from django.urls import path

from .views import RealtimeEventsSSEView, RealtimeMetricsView, RealtimePrometheusMetricsView
from .incidents import IncidentReviewDetailView, IncidentReviewListCreateView


urlpatterns = [
    path("events/", RealtimeEventsSSEView.as_view(), name="realtime-events"),
    path("metrics/", RealtimeMetricsView.as_view(), name="realtime-metrics"),
    path("metrics/prometheus/", RealtimePrometheusMetricsView.as_view(), name="realtime-metrics-prometheus"),
    path("ops/incidents/", IncidentReviewListCreateView.as_view(), name="ops-incidents"),
    path("ops/incidents/<int:pk>/", IncidentReviewDetailView.as_view(), name="ops-incident-detail"),
]

