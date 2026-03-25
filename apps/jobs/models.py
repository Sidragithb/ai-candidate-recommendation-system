from django.conf import settings
from django.db import models


class Job(models.Model):
    recruiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    required_skills = models.TextField(blank=True, default="")
    normalized_required_skills = models.JSONField(blank=True, default=list)
    embedding = models.JSONField(blank=True, default=list)
    embedding_updated_at = models.DateTimeField(blank=True, null=True)
    search_document = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title
