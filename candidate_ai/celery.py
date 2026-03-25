import os

try:
    from celery import Celery
except ModuleNotFoundError:  # pragma: no cover - local fallback when celery isn't installed yet
    Celery = None


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "candidate_ai.settings")

if Celery is not None:
    app = Celery("candidate_ai")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
else:
    class _DummyConf:
        task_always_eager = True


    class _DummyCeleryApp:
        conf = _DummyConf()

        def task(self, *args, **kwargs):
            def decorator(func):
                func.delay = func
                func.apply = lambda args=None, kwargs=None: func(*(args or []), **(kwargs or {}))
                return func

            return decorator

        def autodiscover_tasks(self):
            return None


    app = _DummyCeleryApp()
