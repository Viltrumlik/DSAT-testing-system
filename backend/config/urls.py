from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from users.views import (
    ClientAuthTelemetryIngestView,
    CookieLogoutView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    RevokeAllSessionsView,
    RevokeSessionView,
    SessionListView,
)
from config.health import LiveHealthView, ReadyHealthView
from config.ops_alerting import AlertmanagerWebhookView
from config.csrf_api import CsrfTokenView
from config.csp_report import CSPReportView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/auth/login/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', CookieLogoutView.as_view(), name='token_logout'),
    path('api/auth/csrf/', CsrfTokenView.as_view(), name='csrf-token'),
    path('api/auth/client-telemetry/', ClientAuthTelemetryIngestView.as_view(), name='auth-client-telemetry'),
    path('api/auth/sessions/', SessionListView.as_view(), name='auth-sessions'),
    path('api/auth/sessions/revoke_all/', RevokeAllSessionsView.as_view(), name='auth-revoke-all'),
    path('api/auth/sessions/<int:session_id>/revoke/', RevokeSessionView.as_view(), name='auth-revoke-session'),
    path('api/ops/alertmanager/webhook/', AlertmanagerWebhookView.as_view(), name='alertmanager-webhook'),
    path('api/health/live/', LiveHealthView.as_view(), name='health-live'),
    path('api/health/ready/', ReadyHealthView.as_view(), name='health-ready'),
    path('api/csp-report/', CSPReportView.as_view(), name='csp-report'),
    path("api/schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/schema/swagger/", SpectacularSwaggerView.as_view(url_name="openapi-schema"), name="openapi-swagger"),
    path('api/users/', include('users.urls')),
    path('api/exams/', include('exams.urls')),
    path('api/access/', include('access.urls')),
    # Out-of-scope HTTP surfaces (classes/realtime/vocabulary/assessments/questionbank)
    # are intentionally not routed in the standalone exam-runner repo. The apps stay
    # INSTALLED so their migrations and the exams<->questionbank/classes model graph
    # resolve, but they expose no API.
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
