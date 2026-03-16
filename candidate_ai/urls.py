from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_view(request):
    return JsonResponse({"status": "ok", "framework": "django"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_view),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/jobs/", include("apps.jobs.urls")),
    path("api/candidates/", include("apps.candidates.urls")),
    path("api/chatbot/", include("apps.chatbot.urls")),
    path("api/vapi/", include("apps.vapi.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
