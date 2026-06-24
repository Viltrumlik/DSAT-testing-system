from django.urls import path

from .views import (
    VocabularyWordsView,
    VocabularyDailyView,
    VocabularyReviewView,
    AdminVocabularyWordListCreateView,
    AdminVocabularyWordDetailView,
)


urlpatterns = [
    path("words/", VocabularyWordsView.as_view(), name="vocabulary-words"),
    path("daily/", VocabularyDailyView.as_view(), name="vocabulary-daily"),
    path("review/", VocabularyReviewView.as_view(), name="vocabulary-review"),
    path("admin/words/", AdminVocabularyWordListCreateView.as_view(), name="vocabulary-admin-words"),
    path("admin/words/<int:pk>/", AdminVocabularyWordDetailView.as_view(), name="vocabulary-admin-word-detail"),
]

