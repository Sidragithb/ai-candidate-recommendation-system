import json
from collections import Counter

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.candidates.models import Candidate
from apps.jobs.models import Job


@csrf_exempt
@require_http_methods(["GET", "POST"])
def job_list_create_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    if request.method == "GET":
        jobs = [
            {
                "id": job.id,
                "title": job.title,
                "description": job.description,
                "required_skills": _split_skills(job.required_skills),
                "recruiter_id": job.recruiter_id,
                "created_at": job.created_at.isoformat(),
            }
            for job in Job.objects.filter(recruiter=request.user).order_by("-created_at")
        ]
        return JsonResponse({"jobs": jobs})

    payload = json.loads(request.body or "{}")
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    required_skills = payload.get("required_skills", [])

    if not title or not description:
        return JsonResponse({"detail": "Title and description are required."}, status=400)

    if isinstance(required_skills, str):
        required_skills = [item.strip() for item in required_skills.split(",") if item.strip()]

    job = Job.objects.create(
        recruiter=request.user,
        title=title,
        description=description,
        required_skills=",".join(required_skills),
    )
    return JsonResponse(_serialize_job(job), status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def job_detail_view(request, job_id: int):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    try:
        job = Job.objects.get(id=job_id, recruiter=request.user)
    except Job.DoesNotExist:
        return JsonResponse({"detail": "Job not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_job(job))

    if request.method == "DELETE":
        job.delete()
        return JsonResponse({"detail": "Job deleted."})

    payload = json.loads(request.body or "{}")
    if "title" in payload:
        job.title = str(payload["title"]).strip()
    if "description" in payload:
        job.description = str(payload["description"]).strip()
    if "required_skills" in payload:
        required_skills = payload["required_skills"]
        if isinstance(required_skills, str):
            required_skills = [item.strip() for item in required_skills.split(",") if item.strip()]
        job.required_skills = ",".join(required_skills)
    job.save(update_fields=["title", "description", "required_skills"])
    return JsonResponse(_serialize_job(job))


@require_GET
def dashboard_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    jobs = list(Job.objects.filter(recruiter=request.user).order_by("-created_at"))
    candidates = list(Candidate.objects.select_related("job").filter(job__recruiter=request.user))
    indexed_candidates = [candidate for candidate in candidates if candidate.vector_indexed]
    skill_counter: Counter[str] = Counter()
    for candidate in candidates:
        skill_counter.update(_split_skills(candidate.skills))

    jobs_summary = []
    for job in jobs:
        job_candidates = [candidate for candidate in candidates if candidate.job_id == job.id]
        jobs_summary.append(
            {
                "job_id": job.id,
                "title": job.title,
                "candidate_count": len(job_candidates),
                "indexed_candidate_count": sum(1 for candidate in job_candidates if candidate.vector_indexed),
                "required_skills": _split_skills(job.required_skills),
            }
        )

    return JsonResponse(
        {
            "overview": {
                "total_jobs": len(jobs),
                "total_candidates": len(candidates),
                "indexed_candidates": len(indexed_candidates),
                "top_skills": [
                    {"skill": skill, "count": count}
                    for skill, count in skill_counter.most_common(10)
                ],
            },
            "jobs": jobs_summary,
        }
    )


def _serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "required_skills": _split_skills(job.required_skills),
        "recruiter_id": job.recruiter_id,
        "created_at": job.created_at.isoformat(),
    }


def _split_skills(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
