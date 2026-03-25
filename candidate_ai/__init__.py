# Django project package.
try:
    from candidate_ai.celery import app as celery_app
except ModuleNotFoundError:  # pragma: no cover
    celery_app = None


__all__ = ("celery_app",)
