from django.urls import path

from apps.chatbot.views import compare_candidates_view, search_candidates_view


urlpatterns = [
    path("search/", search_candidates_view, name="chatbot-search"),
    path("compare/", compare_candidates_view, name="chatbot-compare"),
]
