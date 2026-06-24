from django.urls import path

from .vocab_views import VocabAllProgressView, VocabSRSReviewView, VocabTodayView

urlpatterns = [
    path("today/", VocabTodayView.as_view(), name="vocab-today"),
    path("review/", VocabSRSReviewView.as_view(), name="vocab-review-srs"),
    path("all/", VocabAllProgressView.as_view(), name="vocab-all-progress"),
]
