try:
    from celery import shared_task
except ModuleNotFoundError:  # pragma: no cover - fallback for environments without celery installed
    def shared_task(*args, **kwargs):
        def decorator(func):
            class _TaskWrapper:
                app = type("DummyApp", (), {"conf": type("DummyConf", (), {"task_always_eager": True})()})()
                _self = type("DummyTask", (), {})()

                def __call__(self, *call_args, **call_kwargs):
                    return func(self._self, *call_args, **call_kwargs)

                def delay(self, *call_args, **call_kwargs):
                    return func(self._self, *call_args, **call_kwargs)

                def apply(self, args=None, kwargs=None):
                    return func(self._self, *(args or []), **(kwargs or {}))

            return _TaskWrapper()

        return decorator
from django.utils import timezone

from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.hybrid_search import HybridSearchService
from apps.ai.services.ingestion import ResumeIngestionService
from apps.ai.services.text import split_skills
from apps.jobs.models import Job


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def process_candidate_resume_task(self, candidate_id: int):
    candidate = ResumeIngestionService().process_candidate(candidate_id)
    HybridSearchService().invalidate_job_cache(candidate.job_id)
    HybridSearchService().invalidate_job_cache(None)
    return candidate.id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def update_job_embedding_task(self, job_id: int):
    job = Job.objects.get(id=job_id)
    normalized_required_skills = split_skills(job.required_skills)
    search_document = "\n".join(filter(None, [job.title, job.description, " ".join(normalized_required_skills)]))
    embedding = EmbeddingService().embed_text(search_document)
    job.normalized_required_skills = normalized_required_skills
    job.search_document = search_document
    job.embedding = embedding
    job.embedding_updated_at = timezone.now()
    job.save(update_fields=["normalized_required_skills", "search_document", "embedding", "embedding_updated_at"])
    HybridSearchService().invalidate_job_cache(job.id)
    HybridSearchService().invalidate_job_cache(None)
    return job.id
