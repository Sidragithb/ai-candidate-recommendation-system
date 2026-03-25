from django.contrib import admin

from apps.candidates.models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "email",
        "job",
        "processing_status",
        "fit_score",
        "vector_indexed",
        "created_at",
    )
    list_filter = ("processing_status", "vector_indexed", "education_level")
    search_fields = ("full_name", "email", "skills", "resume_text")
