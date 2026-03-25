import json
from collections import Counter

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.permissions import require_authenticated, scoped_candidates, scoped_jobs
from apps.ai.services.text import split_skills
from apps.ai.tasks import update_job_embedding_task
from apps.candidates.models import Candidate
from apps.jobs.models import Job


@csrf_exempt
@require_authenticated
@require_http_methods(["GET", "POST"])
def job_list_create_view(request):
    if request.method == "GET":
        jobs = [
            _serialize_job(job)
            for job in scoped_jobs(request.user, Job.objects.all()).order_by("-created_at")
        ]
        return JsonResponse({"jobs": jobs})

    payload = json.loads(request.body or "{}")
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    required_skills = split_skills(payload.get("required_skills", []))

    if not title or not description:
        return JsonResponse({"detail": "Title and description are required."}, status=400)

    job = Job.objects.create(
        recruiter=request.user,
        title=title,
        description=description,
        required_skills=",".join(required_skills),
        normalized_required_skills=required_skills,
        search_document="\n".join(filter(None, [title, description, " ".join(required_skills)])),
    )
    _enqueue_job_embedding(job.id)
    return JsonResponse(_serialize_job(job), status=201)


@csrf_exempt
@require_authenticated
@require_http_methods(["GET", "PATCH", "DELETE"])
def job_detail_view(request, job_id: int):
    try:
        job = scoped_jobs(request.user, Job.objects.all()).get(id=job_id)
    except Job.DoesNotExist:
        return JsonResponse({"detail": "Job not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_job(job))

    if request.method == "DELETE":
        job.delete()
        return JsonResponse({"detail": "Job deleted."})

    payload = json.loads(request.body or "{}")
    update_fields: list[str] = []
    if "title" in payload:
        job.title = str(payload["title"]).strip()
        update_fields.append("title")
    if "description" in payload:
        job.description = str(payload["description"]).strip()
        update_fields.append("description")
    if "required_skills" in payload:
        required_skills = split_skills(payload["required_skills"])
        job.required_skills = ",".join(required_skills)
        job.normalized_required_skills = required_skills
        update_fields.extend(["required_skills", "normalized_required_skills"])

    job.search_document = "\n".join(
        filter(None, [job.title, job.description, " ".join(job.normalized_required_skills or split_skills(job.required_skills))])
    )
    update_fields.append("search_document")
    job.save(update_fields=update_fields)
    _enqueue_job_embedding(job.id)
    return JsonResponse(_serialize_job(job))


@require_GET
@require_authenticated
def dashboard_view(request):
    jobs = list(scoped_jobs(request.user, Job.objects.all()).order_by("-created_at"))
    candidates = list(scoped_candidates(request.user, Candidate.objects.select_related("job")))
    indexed_candidates = [candidate for candidate in candidates if candidate.vector_indexed]
    processing_candidates = [
        candidate for candidate in candidates if candidate.processing_status != Candidate.ProcessingStatus.COMPLETED
    ]
    skill_counter: Counter[str] = Counter()
    for candidate in candidates:
        skill_counter.update(candidate.parsed_skills or split_skills(candidate.skills))

    jobs_summary = []
    for job in jobs:
        job_candidates = [candidate for candidate in candidates if candidate.job_id == job.id]
        jobs_summary.append(
            {
                "job_id": job.id,
                "title": job.title,
                "candidate_count": len(job_candidates),
                "indexed_candidate_count": sum(1 for candidate in job_candidates if candidate.vector_indexed),
                "avg_fit_score": round(
                    sum(float(candidate.fit_score) for candidate in job_candidates) / max(len(job_candidates), 1),
                    2,
                ),
                "required_skills": job.normalized_required_skills or split_skills(job.required_skills),
                "embedding_ready": bool(job.embedding),
            }
        )

    return JsonResponse(
        {
            "overview": {
                "total_jobs": len(jobs),
                "total_candidates": len(candidates),
                "indexed_candidates": len(indexed_candidates),
                "processing_candidates": len(processing_candidates),
                "top_skills": [
                    {"skill": skill, "count": count}
                    for skill, count in skill_counter.most_common(10)
                ],
            },
            "jobs": jobs_summary,
        }
    )


def _enqueue_job_embedding(job_id: int) -> None:
    if update_job_embedding_task.app.conf.task_always_eager:
        update_job_embedding_task.apply(args=[job_id])
    else:
        update_job_embedding_task.delay(job_id)


def _serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "required_skills": job.normalized_required_skills or split_skills(job.required_skills),
        "recruiter_id": job.recruiter_id,
        "embedding_ready": bool(job.embedding),
        "embedding_updated_at": job.embedding_updated_at.isoformat() if job.embedding_updated_at else None,
        "created_at": job.created_at.isoformat(),
    }
