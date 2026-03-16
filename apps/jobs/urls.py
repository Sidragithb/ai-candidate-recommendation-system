from django.urls import path

from apps.jobs.views import dashboard_view, job_detail_view, job_list_create_view


urlpatterns = [
    path("dashboard/", dashboard_view, name="job-dashboard"),
    path("", job_list_create_view, name="job-list-create"),
    path("<int:job_id>/", job_detail_view, name="job-detail"),
]
