import hashlib
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.ai.services.document_parser import DocumentParserService
from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.vector_store import VectorSearchService
from apps.candidates.models import Candidate
from apps.jobs.models import Job

ALLOWED_RESUME_EXTENSIONS = {".pdf"}


@require_GET
def candidate_list_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    job_id = request.GET.get("job_id")
    candidates = Candidate.objects.select_related("job").filter(job__recruiter=request.user)
    if job_id:
        candidates = candidates.filter(job_id=job_id)

    data = [
        {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "email": candidate.email,
            "skills": _split_skills(candidate.skills),
            "job_id": candidate.job_id,
            "resume_file": candidate.resume_file.url if candidate.resume_file else None,
            "vector_indexed": candidate.vector_indexed,
            "estimated_years_experience": float(candidate.estimated_years_experience),
            "experience_score": float(candidate.experience_score),
            "education_level": candidate.education_level,
            "education_score": float(candidate.education_score),
            "created_at": candidate.created_at.isoformat(),
        }
        for candidate in candidates.order_by("-created_at")
    ]
    return JsonResponse({"candidates": data})


@require_GET
def candidate_summary_view(request, candidate_id: int):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    try:
        candidate = Candidate.objects.select_related("job").get(
            id=candidate_id,
            job__recruiter=request.user,
        )
    except Candidate.DoesNotExist:
        return JsonResponse({"detail": "Candidate not found."}, status=404)

    resume_excerpt = (candidate.resume_text or "").strip()
    if len(resume_excerpt) > 400:
        resume_excerpt = resume_excerpt[:400].rstrip() + "..."

    return JsonResponse(
        {
            "candidate": {
                "id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "skills": _split_skills(candidate.skills),
                "job_id": candidate.job_id,
                "job_title": candidate.job.title,
                "vector_indexed": candidate.vector_indexed,
                "estimated_years_experience": float(candidate.estimated_years_experience),
                "experience_score": float(candidate.experience_score),
                "education_level": candidate.education_level,
                "education_score": float(candidate.education_score),
                "created_at": candidate.created_at.isoformat(),
            },
            "summary": {
                "headline": f"{candidate.full_name} applied for {candidate.job.title}.",
                "skills_summary": ", ".join(_split_skills(candidate.skills)) or "No skills listed.",
                "resume_excerpt": resume_excerpt or "No resume text available.",
                "experience_summary": (
                    f"Estimated experience: {candidate.estimated_years_experience} years."
                    if candidate.estimated_years_experience
                    else "Estimated experience not detected."
                ),
                "education_summary": candidate.education_level or "Education level not detected.",
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

    if Candidate.objects.filter(job=job, email__iexact=email).exists():
        return JsonResponse(
            {"detail": "A candidate with this email has already applied for this job."},
            status=409,
        )

    resume_extension = Path(resume.name).suffix.lower()
    if resume_extension not in ALLOWED_RESUME_EXTENSIONS:
        return JsonResponse(
            {"detail": "Unsupported resume format. Only PDF resumes are allowed."},
            status=400,
        )

    file_bytes = resume.read()
    resume_hash = hashlib.sha256(file_bytes).hexdigest()
    if Candidate.objects.filter(job=job, resume_hash=resume_hash).exists():
        return JsonResponse(
            {"detail": "This resume content has already been uploaded for this job."},
            status=409,
        )

    candidate = Candidate(
        job=job,
        full_name=full_name,
        email=email,
        skills=skills,
        resume_hash=resume_hash,
    )

    candidate.resume_file.save(resume.name, ContentFile(file_bytes), save=False)
    resume_text = DocumentParserService().extract_text(resume.name, file_bytes)
    candidate.resume_text = resume_text

    if not resume_text.strip():
        return JsonResponse(
            {"detail": "Could not extract readable text from the uploaded resume."},
            status=400,
        )

    years_experience = _estimate_years_experience(resume_text)
    education_level = _detect_education_level(resume_text)
    candidate.estimated_years_experience = years_experience
    candidate.experience_score = _experience_score(years_experience)
    candidate.education_level = education_level
    candidate.education_score = _education_score(education_level)

    candidate.save()

    if resume_text:
        combined_text = "\n".join(filter(None, [candidate.full_name, candidate.skills, candidate.resume_text]))
        embedding = EmbeddingService().embed_text(combined_text)
        try:
            VectorSearchService().index_candidate(
                candidate_id=candidate.id,
                job_id=candidate.job_id,
                full_name=candidate.full_name,
                email=candidate.email,
                skills=_split_skills(candidate.skills),
                resume_text=candidate.resume_text,
                years_experience=float(candidate.estimated_years_experience),
                experience_score=float(candidate.experience_score),
                education_level=candidate.education_level,
                education_score=float(candidate.education_score),
                embedding=embedding,
            )
            candidate.vector_indexed = True
            candidate.save(update_fields=["vector_indexed"])
        except Exception:
            pass

    return JsonResponse(
        {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "email": candidate.email,
            "skills": _split_skills(candidate.skills),
            "job_id": candidate.job_id,
            "vector_indexed": candidate.vector_indexed,
            "estimated_years_experience": float(candidate.estimated_years_experience),
            "experience_score": float(candidate.experience_score),
            "education_level": candidate.education_level,
            "education_score": float(candidate.education_score),
        },
        status=201,
    )


def _split_skills(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _estimate_years_experience(resume_text: str) -> float:
    text = resume_text.lower()
    numeric_matches = re.findall(r"(\d+(?:\.\d+)?)\+?\s+years?", text)
    if numeric_matches:
        return max(float(value) for value in numeric_matches)

    start_years = [int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if len(start_years) >= 2:
        span = max(start_years) - min(start_years)
        return float(max(span, 0))
    return 0.0


def _experience_score(years_experience: float) -> float:
    return min(round(years_experience / 6.0, 3), 1.0)


def _detect_education_level(resume_text: str) -> str:
    text = resume_text.lower()
    if any(token in text for token in ["phd", "doctor of philosophy"]):
        return "PhD"
    if any(token in text for token in ["master", "msc", "ms ", "m.s.", "mba"]):
        return "Masters"
    if any(token in text for token in ["bachelor", "bs ", "b.s.", "bsc", "b.s", "b.e", "be "]):
        return "Bachelors"
    if any(token in text for token in ["intermediate", "college", "fsc", "a-level"]):
        return "Intermediate"
    return ""


def _education_score(education_level: str) -> float:
    score_map = {
        "PhD": 1.0,
        "Masters": 0.85,
        "Bachelors": 0.7,
        "Intermediate": 0.4,
        "": 0.0,
    }
    return score_map.get(education_level, 0.0)
