from django.db import models

from apps.jobs.models import Job


class Candidate(models.Model):
    class ProcessingStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="candidates")
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    skills = models.TextField(blank=True, default="")
    parsed_skills = models.JSONField(blank=True, default=list)
    resume_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    resume_file = models.FileField(upload_to="resumes/", blank=True, null=True)
    resume_text = models.TextField(blank=True, default="")
    parsed_resume = models.JSONField(blank=True, default=dict)
    embedding = models.JSONField(blank=True, default=list)
    search_document = models.TextField(blank=True, default="")
    vector_indexed = models.BooleanField(default=False)
    estimated_years_experience = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    experience_score = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    education_level = models.CharField(max_length=64, blank=True, default="")
    degree_title = models.CharField(max_length=255, blank=True, default="")
    education_institution = models.CharField(max_length=255, blank=True, default="")
    education_score = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    fit_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fit_breakdown = models.JSONField(blank=True, default=dict)
    ranking_reasons = models.JSONField(blank=True, default=list)
    processing_status = models.CharField(
        max_length=32,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.QUEUED,
    )
    processing_error = models.TextField(blank=True, default="")
    last_processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.full_name} - {self.job.title}"
