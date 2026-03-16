from django.urls import path

from apps.vapi.views import vapi_hiring_assistant_webhook


urlpatterns = [
    path("hiring-assistant/", vapi_hiring_assistant_webhook, name="vapi-hiring-assistant"),
]
