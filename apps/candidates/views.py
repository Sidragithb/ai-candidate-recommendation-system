from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import require_authenticated, scoped_candidates, scoped_jobs
from apps.ai.services.ingestion import ConflictError, ResumeIngestionService
from apps.ai.services.text import split_skills
from apps.ai.tasks import process_candidate_resume_task
from apps.candidates.models import Candidate
from apps.jobs.models import Job


@require_GET
@require_authenticated
def candidate_list_view(request):
    job_id = request.GET.get("job_id")
    candidates = scoped_candidates(request.user, Candidate.objects.select_related("job"))
    if job_id:
        candidates = candidates.filter(job_id=job_id)

    data = [_serialize_candidate(candidate) for candidate in candidates.order_by("-created_at")]
    return JsonResponse({"candidates": data})


@require_GET
@require_authenticated
def candidate_summary_view(request, candidate_id: int):
    try:
        candidate = scoped_candidates(request.user, Candidate.objects.select_related("job")).get(id=candidate_id)
    except Candidate.DoesNotExist:
        return JsonResponse({"detail": "Candidate not found."}, status=404)

    resume_excerpt = (candidate.resume_text or "").strip()
    if len(resume_excerpt) > 400:
        resume_excerpt = resume_excerpt[:400].rstrip() + "..."

    return JsonResponse(
        {
            "candidate": _serialize_candidate(candidate),
            "summary": {
                "headline": f"{candidate.full_name} applied for {candidate.job.title}.",
                "skills_summary": ", ".join(candidate.parsed_skills or split_skills(candidate.skills)) or "No skills listed.",
                "resume_excerpt": resume_excerpt or "Resume is still processing.",
                "experience_summary": (
                    f"Estimated experience: {candidate.estimated_years_experience} years."
                    if candidate.estimated_years_experience
                    else "Estimated experience not detected."
                ),
                "education_summary": (
                    " | ".join(
                        part
                        for part in [
                            candidate.education_level,
                            candidate.degree_title,
                            candidate.education_institution,
                        ]
                        if part
                    )
                    or "Education details not detected."
                ),
                "fit_summary": {
                    "fit_score": float(candidate.fit_score),
                    "reasons": list(candidate.ranking_reasons or []),
                    "breakdown": dict(candidate.fit_breakdown or {}),
                },
            },
        }
    )


@csrf_exempt
@require_POST
def candidate_apply_view(request):
    job_id = request.POST.get("job_id")
    full_name = str(request.POST.get("full_name", "")).strip()
    email = str(request.POST.get("email", "")).strip()
    skills = str(request.POST.get("skills", "")).strip()
    resume = request.FILES.get("resume")

    if not job_id or not full_name or not email:
        return JsonResponse({"detail": "job_id, full_name, and email are required."}, status=400)
    if resume is None:
        return JsonResponse({"detail": "Resume file is required."}, status=400)

    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return JsonResponse({"detail": "Job not found."}, status=404)

    try:
        candidate = ResumeIngestionService().create_candidate(
            job=job,
            full_name=full_name,
            email=email,
            skills=skills,
            resume_name=resume.name,
            file_bytes=resume.read(),
        )
    except ConflictError as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    _enqueue_candidate_processing(candidate.id)
    return JsonResponse(
        {
            "detail": "Resume upload accepted and queued for background processing.",
            "candidate": _serialize_candidate(candidate),
        },
        status=202,
    )


@csrf_exempt
@require_POST
@require_authenticated
def candidate_bulk_upload_view(request):
    job_id = request.POST.get("job_id")
    if not job_id:
        return JsonResponse({"detail": "job_id is required."}, status=400)

    try:
        job = scoped_jobs(request.user, Job.objects.all()).get(id=job_id)
    except Job.DoesNotExist:
        return JsonResponse({"detail": "Job not found."}, status=404)

    resumes = request.FILES.getlist("resumes")
    if not resumes:
        return JsonResponse({"detail": "At least one resume file is required."}, status=400)

    created: list[dict] = []
    errors: list[dict] = []
    for resume in resumes:
        base_name = Path(resume.name).stem.replace("_", " ").replace("-", " ").strip() or "Unknown Candidate"
        email = f"{Path(resume.name).stem.lower().replace(' ', '.')}@pending.local"
        try:
            candidate = ResumeIngestionService().create_candidate(
                job=job,
                full_name=base_name.title(),
                email=email[:200],
                skills="",
                resume_name=resume.name,
                file_bytes=resume.read(),
            )
            _enqueue_candidate_processing(candidate.id)
            created.append(_serialize_candidate(candidate))
        except Exception as exc:
            errors.append({"file": resume.name, "detail": str(exc)})

    return JsonResponse(
        {
            "detail": "Bulk upload request processed.",
            "created_count": len(created),
            "error_count": len(errors),
            "created": created,
            "errors": errors,
        },
        status=202,
    )


def _enqueue_candidate_processing(candidate_id: int) -> None:
    if process_candidate_resume_task.app.conf.task_always_eager:
        process_candidate_resume_task.apply(args=[candidate_id])
    else:
        process_candidate_resume_task.delay(candidate_id)


def _serialize_candidate(candidate: Candidate) -> dict:
    return {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "skills": candidate.parsed_skills or split_skills(candidate.skills),
        "job_id": candidate.job_id,
        "job_title": candidate.job.title if hasattr(candidate, "job") else None,
        "resume_file": candidate.resume_file.url if candidate.resume_file else None,
        "vector_indexed": candidate.vector_indexed,
        "processing_status": candidate.processing_status,
        "processing_error": candidate.processing_error,
        "estimated_years_experience": float(candidate.estimated_years_experience),
        "experience_score": float(candidate.experience_score),
        "education_level": candidate.education_level,
        "degree_title": candidate.degree_title,
        "education_institution": candidate.education_institution,
        "education_score": float(candidate.education_score),
        "fit_score": float(candidate.fit_score),
        "fit_breakdown": dict(candidate.fit_breakdown or {}),
        "ranking_reasons": list(candidate.ranking_reasons or []),
        "created_at": candidate.created_at.isoformat(),
        "last_processed_at": candidate.last_processed_at.isoformat() if candidate.last_processed_at else None,
    }
