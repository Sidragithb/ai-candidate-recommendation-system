from django.urls import path

from apps.candidates.views import candidate_apply_view, candidate_list_view, candidate_summary_view


urlpatterns = [
    path("", candidate_list_view, name="candidate-list"),
    path("apply/", candidate_apply_view, name="candidate-apply"),
    path("<int:candidate_id>/summary/", candidate_summary_view, name="candidate-summary"),
]
