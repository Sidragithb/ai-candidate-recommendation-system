import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.ai.services.assistant import AssistantResponseService
from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.vector_store import VectorSearchService
from apps.candidates.models import Candidate
from apps.jobs.models import Job


@csrf_exempt
def search_candidates_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Use POST."}, status=405)

    payload = json.loads(request.body or "{}")
    query = str(payload.get("query", "")).strip()
    job_id = payload.get("job_id")
    job_title = str(payload.get("job_title", "")).strip()
    limit = int(payload.get("limit", 5))

    if not query:
        return JsonResponse({"detail": "Query is required."}, status=400)
    resolved_job_id, resolved_job_title = _resolve_job_reference(job_id=job_id, job_title=job_title)
    if job_id is not None or job_title:
        if resolved_job_id is None:
            return JsonResponse({"detail": "Job not found for the provided job_id or job_title."}, status=404)

    embedding = EmbeddingService().embed_text(query)
    try:
        matches = VectorSearchService().search_candidates(
            query_embedding=embedding,
            query_text=query,
            job_id=resolved_job_id,
            limit=limit,
        )
        data = [match.model_dump() for match in matches]
    except Exception:
        matches = []
        data = []

    response_payload = AssistantResponseService().build_response(
        query=query,
        matches=matches,
        job_id=resolved_job_id,
    )

    return JsonResponse(
        {
            "query": query,
            "job_id": resolved_job_id,
            "job_title": resolved_job_title,
            "matches": data,
            "answer": response_payload["answer"],
            "summary": response_payload["summary"],
            "assistant_provider": response_payload["provider"],
            "assistant_model": response_payload["model"],
        }
    )


@csrf_exempt
def compare_candidates_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Use POST."}, status=405)

    payload = json.loads(request.body or "{}")
    candidate_ids = payload.get("candidate_ids", [])
    query = str(payload.get("query", "")).strip() or "Compare these candidates for relevance."

    if not isinstance(candidate_ids, list) or len(candidate_ids) < 2:
        return JsonResponse(
            {"detail": "Provide at least two candidate IDs in candidate_ids."},
            status=400,
        )

    candidates = list(
        Candidate.objects.filter(id__in=candidate_ids)
        .select_related("job")
        .order_by("id")
    )
    if len(candidates) < 2:
        return JsonResponse({"detail": "Not enough valid candidates found."}, status=404)

    query_terms = _extract_query_terms(query)
    comparison_rows = []
    for candidate in candidates:
        skills = [item.strip() for item in candidate.skills.split(",") if item.strip()]
        matched_skills = [skill for skill in skills if _skill_matches_query(skill, query_terms)]
        comparison_rows.append(
            {
                "candidate_id": candidate.id,
                "full_name": candidate.full_name,
                "job_id": candidate.job_id,
                "job_title": candidate.job.title,
                "skills": skills,
                "matched_skills": matched_skills,
                "match_score": round(len(matched_skills) / max(len(query_terms), 1), 4),
                "vector_indexed": candidate.vector_indexed,
            }
        )

    ranked = sorted(
        comparison_rows,
        key=lambda row: (row["match_score"], len(row["skills"]), row["vector_indexed"]),
        reverse=True,
    )
    best = ranked[0]
    others = ranked[1:]

    answer_parts = [
        f"For '{query}', {best['full_name']} appears strongest based on listed skills and indexed resume data."
    ]
    if best["skills"]:
        answer_parts.append(
            "Top matched skills: "
            + (", ".join(best["matched_skills"][:6]) or ", ".join(best["skills"][:6]))
            + "."
        )
    if others:
        answer_parts.append(
            "Compared candidates: "
            + ", ".join(
                f"{candidate['full_name']} ({', '.join(candidate['skills'][:3]) or 'no listed skills'})"
                for candidate in others
            )
            + "."
        )

    return JsonResponse(
        {
            "query": query,
            "candidates": comparison_rows,
            "best_candidate": best,
            "answer": " ".join(answer_parts),
        }
    )


def _extract_query_terms(query_text: str) -> set[str]:
    stop_words = {
        "best",
        "candidate",
        "candidates",
        "compare",
        "for",
        "the",
        "and",
        "with",
        "job",
    }
    cleaned = query_text.replace(",", " ").replace("/", " ").lower()
    return {
        token.strip()
        for token in cleaned.split()
        if token.strip() and token.strip() not in stop_words
    }


def _skill_matches_query(skill: str, query_terms: set[str]) -> bool:
    normalized_skill = skill.lower().strip()
    if not query_terms:
        return False
    if normalized_skill in query_terms:
        return True
    return any(term in normalized_skill or normalized_skill in term for term in query_terms)


def _resolve_job_reference(job_id=None, job_title: str = "") -> tuple[int | None, str | None]:
    if job_id is not None:
        try:
            job = Job.objects.get(id=job_id)
            return job.id, job.title
        except Job.DoesNotExist:
            return None, None

    if job_title:
        normalized_title = " ".join(job_title.lower().split())
        title_terms = [term for term in normalized_title.split() if term]
        filters = Q(title__iexact=job_title) | Q(title__icontains=job_title)
        for term in title_terms:
            filters |= Q(title__icontains=term)

        jobs = list(
            Job.objects.filter(filters)
            .annotate(
                candidate_count=Count("candidates", distinct=True),
                indexed_candidate_count=Count(
                    "candidates",
                    filter=Q(candidates__vector_indexed=True),
                    distinct=True,
                ),
            )
            .order_by("-created_at")
        )
        if jobs:
            jobs.sort(
                key=lambda job: (
                    job.indexed_candidate_count,
                    job.candidate_count,
                    normalized_title in " ".join(job.title.lower().split()),
                    sum(term in job.title.lower() for term in title_terms),
                    " ".join(job.title.lower().split()) == normalized_title,
                    job.created_at,
                ),
                reverse=True,
            )
            selected_job = jobs[0]
            return selected_job.id, selected_job.title
        return None, None

    return None, None
