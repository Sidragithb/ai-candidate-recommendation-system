from django.contrib import admin

from apps.candidates.models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "email", "job", "vector_indexed", "created_at")
    search_fields = ("full_name", "email", "skills")
