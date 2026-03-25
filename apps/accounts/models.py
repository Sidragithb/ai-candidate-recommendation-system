from django.conf import settings
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    RECRUITER = "recruiter", "Recruiter"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=32,
        choices=UserRole.choices,
        default=UserRole.RECRUITER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"
