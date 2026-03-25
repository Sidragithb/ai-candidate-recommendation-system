from django.contrib import admin

from apps.jobs.models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "recruiter", "embedding_updated_at", "created_at")
    search_fields = ("title", "description")
