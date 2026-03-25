from functools import wraps

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from apps.accounts.models import UserProfile, UserRole


User = get_user_model()


def ensure_user_profile(user) -> UserProfile:
    if not user or not getattr(user, "is_authenticated", False):
        raise ValueError("Authenticated user is required.")

    default_role = UserRole.ADMIN if User.objects.count() == 1 else UserRole.RECRUITER
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": default_role},
    )
    if created and default_role != profile.role:
        profile.role = default_role
        profile.save(update_fields=["role"])
    return profile


def get_user_role(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    return ensure_user_profile(user).role


def is_admin(user) -> bool:
    return get_user_role(user) == UserRole.ADMIN


def can_manage_job(user, job) -> bool:
    return bool(user and user.is_authenticated and (is_admin(user) or job.recruiter_id == user.id))


def scoped_jobs(user, queryset):
    if is_admin(user):
        return queryset
    return queryset.filter(recruiter=user)


def scoped_candidates(user, queryset):
    if is_admin(user):
        return queryset
    return queryset.filter(job__recruiter=user)


def require_authenticated(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Authentication required."}, status=401)
        ensure_user_profile(request.user)
        return view_func(request, *args, **kwargs)

    return _wrapped


def require_roles(*allowed_roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"detail": "Authentication required."}, status=401)
            role = get_user_role(request.user)
            if role not in allowed_roles:
                return JsonResponse({"detail": "You do not have permission for this action."}, status=403)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
