import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.permissions import require_authenticated, scoped_candidates, scoped_jobs
from apps.ai.services.assistant import AssistantResponseService
from apps.ai.services.hybrid_search import HybridSearchService
from apps.ai.services.text import infer_education_level, split_skills, tokenize_keywords
from apps.candidates.models import Candidate
from apps.jobs.models import Job


@csrf_exempt
@require_authenticated
def search_candidates_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Use POST."}, status=405)

    payload = json.loads(request.body or "{}")
    query = str(payload.get("query", "")).strip()
    job_id = payload.get("job_id")
    limit = int(payload.get("limit", 5))

    if not query:
        return JsonResponse({"detail": "Query is required."}, status=400)

    job = None
    if job_id is not None:
        try:
            job = scoped_jobs(request.user, Job.objects.all()).get(id=job_id)
        except Job.DoesNotExist:
            return JsonResponse({"detail": "Job not found."}, status=404)

    matches = HybridSearchService().search(query=query, job=job, limit=limit)
    response_payload = AssistantResponseService().build_response(
        query=query,
        matches=matches,
        job_id=job.id if job else None,
    )

    return JsonResponse(
        {
            "query": query,
            "job_id": job.id if job else None,
            "job_title": job.title if job else None,
            "matches": [match.model_dump() for match in matches],
            "answer": response_payload["answer"],
            "summary": response_payload["summary"],
            "assistant_provider": response_payload["provider"],
            "assistant_model": response_payload["model"],
            "cached": response_payload.get("cached", False),
        }
    )


@csrf_exempt
@require_authenticated
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
        scoped_candidates(request.user, Candidate.objects.filter(id__in=candidate_ids).select_related("job")).order_by("id")
    )
    if len(candidates) < 2:
        return JsonResponse({"detail": "Not enough valid candidates found."}, status=404)

    query_terms = set(tokenize_keywords(query))
    education_query = _parse_education_query(query)
    is_education_query = bool(education_query["levels"] or education_query["fields"])
    comparison_rows = []
    for candidate in candidates:
        skills = candidate.parsed_skills or split_skills(candidate.skills)
        matched_skills = [] if is_education_query else [skill for skill in skills if skill.lower() in query_terms]
        matched_education = _candidate_education_hits(candidate, education_query)
        match_score = (
            round(len(matched_education) / max(len(education_query["levels"]) + len(education_query["fields"]), 1), 4)
            if is_education_query
            else round(len(matched_skills) / max(len(query_terms), 1), 4)
        )
        comparison_rows.append(
            {
                "candidate_id": candidate.id,
                "full_name": candidate.full_name,
                "job_id": candidate.job_id,
                "job_title": candidate.job.title,
                "skills": skills,
                "matched_skills": matched_skills,
                "matched_education": matched_education,
                "fit_score": float(candidate.fit_score),
                "match_score": match_score,
                "vector_indexed": candidate.vector_indexed,
                "ranking_reasons": list(candidate.ranking_reasons or []),
                "education_level": candidate.education_level,
                "degree_title": candidate.degree_title,
                "education_institution": candidate.education_institution,
            }
        )

    ranked = sorted(
        comparison_rows,
        key=lambda row: (row["fit_score"], row["match_score"], row["vector_indexed"]),
        reverse=True,
    )
    best = ranked[0]
    others = ranked[1:]

    answer_parts = [
        f"For '{query}', {best['full_name']} is strongest with a fit score of {best['fit_score']:.2f}%.",
    ]
    if is_education_query and best["matched_education"]:
        answer_parts.append("Top education match: " + ", ".join(best["matched_education"][:4]) + ".")
    elif best["matched_skills"]:
        answer_parts.append("Top matched skills: " + ", ".join(best["matched_skills"][:6]) + ".")
    if best["ranking_reasons"]:
        answer_parts.append("Why selected: " + " ".join(best["ranking_reasons"][:2]))
    if others:
        answer_parts.append(
            "Alternatives: "
            + ", ".join(f"{candidate['full_name']} ({candidate['fit_score']:.2f}%)" for candidate in others[:3])
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


def _parse_education_query(query: str) -> dict:
    lowered = query.lower()
    levels = set()
    if "bachelor" in lowered or "bachelors" in lowered or "bsc" in lowered or "bs " in f"{lowered} ":
        levels.add("Bachelors")
    if "master" in lowered or "masters" in lowered or "msc" in lowered or "mba" in lowered:
        levels.add("Masters")
    if "phd" in lowered:
        levels.add("PhD")

    fields = set()
    for phrase in ("computer science", "software engineering", "information technology", "computing"):
        if phrase in lowered:
            fields.add(phrase)
    return {"levels": levels, "fields": fields}


def _candidate_education_hits(candidate: Candidate, education_query: dict) -> list[str]:
    hits: list[str] = []
    degree = (candidate.degree_title or "").strip()
    institution = (candidate.education_institution or "").strip()
    level = candidate.education_level or infer_education_level(degree)
    if education_query["levels"] and level in education_query["levels"]:
        hits.append(level)
    lowered_degree = degree.lower()
    lowered_institution = institution.lower()
    for field in education_query["fields"]:
        if field in lowered_degree and degree:
            hits.append(degree)
            break
        if field in lowered_institution and institution:
            hits.append(institution)
            break
    return hits
