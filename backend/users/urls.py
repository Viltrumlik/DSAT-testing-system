from django.urls import path
from .views import (
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserDeleteView,
    UserRegistrationView,
    UserMeView,
    GoogleAuthView,
    TelegramAuthView,
    TelegramOAuthCallbackView,
    TelegramOAuthStartView,
    TelegramWidgetConfigView,
    TelegramLinkView,
    ExamDateOptionListView,
    ExamDateOptionAdminListCreateView,
    ExamDateOptionAdminDetailView,
)
from .prometheus_security import AdminSecurityPrometheusMetricsView

urlpatterns = [
    path('me/', UserMeView.as_view(), name='user-me'),
    path('exam-dates/', ExamDateOptionListView.as_view(), name='exam-date-options'),
    path('admin/exam-dates/', ExamDateOptionAdminListCreateView.as_view(), name='admin-exam-dates'),
    path('admin/exam-dates/<int:pk>/', ExamDateOptionAdminDetailView.as_view(), name='admin-exam-date-detail'),
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    path('google/', GoogleAuthView.as_view(), name='google-auth'),
    path('telegram/config/', TelegramWidgetConfigView.as_view(), name='telegram-widget-config'),
    path('telegram/link/', TelegramLinkView.as_view(), name='telegram-link'),
    path('telegram/start/', TelegramOAuthStartView.as_view(), name='telegram-oauth-start'),
    path('telegram/callback/', TelegramOAuthCallbackView.as_view(), name='telegram-oauth-callback'),
    path('telegram/', TelegramAuthView.as_view(), name='telegram-auth'),
    path('admin/security/metrics/prometheus/', AdminSecurityPrometheusMetricsView.as_view(), name='admin-security-metrics'),
    path('admin/list/', UserListView.as_view(), name='admin-user-list'),
    path('', UserListView.as_view(), name='user-list'),
    path('create/', UserCreateView.as_view(), name='user-create'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),
]
