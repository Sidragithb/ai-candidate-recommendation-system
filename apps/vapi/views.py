import json
import logging

from django.conf import settings
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.ai.services.assistant import AssistantResponseService
from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.vector_store import VectorSearchService
from apps.candidates.models import Candidate
from apps.jobs.models import Job


logger = logging.getLogger(__name__)

HIRING_PROMPT = """
## Role
You are Ava, an AI Hiring Assistant for recruiters.
You help recruiters identify the best candidates for a job based on job requirements, candidate skills, and semantic resume matching.

## Responsibilities
- Answer questions about the best candidate for a job
- List top relevant candidates
- Summarize a candidate profile
- Compare multiple candidates
- Use tools whenever candidate data is needed

## Tool Rules
- If the recruiter asks for best candidates, call `search_candidates`
- If the recruiter asks for a candidate summary, call `get_candidate_summary`
- If the recruiter asks to compare candidates, call `compare_candidates`
- If the recruiter asks which jobs are available, call `list_jobs`
- If the recruiter refers to a role by title, such as "Python Developer", use `job_title`
- If the recruiter gives a numeric job reference, use `job_id`
- Do not ask for a job ID if the recruiter already gave a clear job title
- Never invent candidates, skills, scores, or jobs

## Answer Style
- Be concise, professional, and recruiter-friendly
- Keep answers short by default: 1-3 sentences unless the recruiter explicitly asks for more detail
- Mention the best candidate clearly
- Mention alternatives only when the recruiter explicitly asks for top candidates or comparison
- If no candidates are found, say so directly
- If the recruiter does not specify a job and multiple jobs may exist, first clarify which job they mean
- Do not repeat menus, options, or next-step suggestions after every answer
- Ask at most one short follow-up question only when clarification is required
- When listing jobs, say only the job titles unless the recruiter asks for details
- When answering a direct question, stop after the answer instead of adding extra offers like compare, summary, outreach, or resume
"""


def _json_schema(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _build_hiring_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_candidates",
                "description": "Search the most relevant candidates for a specific job and recruiter query.",
                "parameters": _json_schema(
                    {
                        "job_id": {"type": "integer", "description": "Job ID to search against"},
                        "job_title": {
                            "type": "string",
                            "description": "Job title to search against when job ID is not provided",
                        },
                        "query": {"type": "string", "description": "Recruiter question or search text"},
                        "limit": {"type": "integer", "description": "Maximum number of candidates to return"},
                    },
                    required=["query"],
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_candidate_summary",
                "description": "Get a concise summary of one candidate.",
                "parameters": _json_schema(
                    {"candidate_id": {"type": "integer", "description": "Candidate ID"}},
                    required=["candidate_id"],
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_candidates",
                "description": "Compare multiple candidates for a hiring question.",
                "parameters": _json_schema(
                    {
                        "candidate_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of candidate IDs to compare",
                        },
                        "query": {"type": "string", "description": "Comparison prompt from recruiter"},
                    },
                    required=["candidate_ids", "query"],
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_jobs",
                "description": "List available jobs in the system.",
                "parameters": _json_schema({}),
            },
        },
    ]


def _build_assistant_payload():
    return {
        "assistant": {
            "name": settings.VAPI_ASSISTANT_NAME,
            "model": {
                "provider": "openai",
                "model": settings.ASSISTANT_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": HIRING_PROMPT,
                    }
                ],
                "tools": _build_hiring_tools(),
            },
            "voice": {
                "provider": settings.VAPI_VOICE_PROVIDER,
                "voiceId": settings.VAPI_VOICE_ID,
            },
            "firstMessage": settings.VAPI_FIRST_MESSAGE,
        }
    }


def _parse_arguments(raw_args):
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except Exception:
            return {"raw": raw_args}
    return {}


def _candidate_summary(candidate: Candidate) -> dict:
    skills = [item.strip() for item in candidate.skills.split(",") if item.strip()]
    excerpt = (candidate.resume_text or "").strip()
    if len(excerpt) > 350:
        excerpt = excerpt[:350].rstrip() + "..."
    return {
        "candidate_id": candidate.id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "job_id": candidate.job_id,
        "job_title": candidate.job.title,
        "skills": skills,
        "vector_indexed": candidate.vector_indexed,
        "education_level": candidate.education_level,
        "degree_title": candidate.degree_title,
        "education_institution": candidate.education_institution,
        "resume_excerpt": excerpt or "No resume text available.",
    }


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


def _execute_tool(name: str, args: dict) -> dict:
    if name == "search_candidates":
        query = str(args.get("query", "")).strip()
        job_id = args.get("job_id")
        job_title = str(args.get("job_title", "")).strip()
        limit = int(args.get("limit", 5))
        resolved_job_id, resolved_job_title = _resolve_job_reference(job_id=job_id, job_title=job_title)
        if not query:
            return {"ok": False, "message": "query is required."}
        if (job_id is not None or job_title) and resolved_job_id is None:
            return {"ok": False, "message": "Could not find a matching job for the provided ID or title."}

        embedding = EmbeddingService().embed_text(query)
        matches = VectorSearchService().search_candidates(
            query_embedding=embedding,
            query_text=query,
            job_id=resolved_job_id,
            limit=limit,
        )
        response_payload = AssistantResponseService().build_response(
            query=query,
            matches=matches,
            job_id=resolved_job_id,
        )
        return {
            "ok": True,
            "job_id": resolved_job_id,
            "job_title": resolved_job_title,
            "matches": [match.model_dump() for match in matches],
            "answer": response_payload["answer"],
            "summary": response_payload["summary"],
        }

    if name == "get_candidate_summary":
        candidate_id = args.get("candidate_id")
        if candidate_id is None:
            return {"ok": False, "message": "candidate_id is required."}
        try:
            candidate = Candidate.objects.select_related("job").get(id=candidate_id)
        except Candidate.DoesNotExist:
            return {"ok": False, "message": "Candidate not found."}
        return {"ok": True, "candidate": _candidate_summary(candidate)}

    if name == "compare_candidates":
        candidate_ids = args.get("candidate_ids", [])
        query = str(args.get("query", "")).strip() or "Compare these candidates."
        if not isinstance(candidate_ids, list) or len(candidate_ids) < 2:
            return {"ok": False, "message": "Provide at least two candidate IDs."}

        candidates = list(Candidate.objects.filter(id__in=candidate_ids).select_related("job").order_by("id"))
        if len(candidates) < 2:
            return {"ok": False, "message": "Not enough valid candidates found."}

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
        return {
            "ok": True,
            "best_candidate": best,
            "candidates": comparison_rows,
            "message": f"{best['full_name']} appears strongest for the comparison query.",
        }

    if name == "list_jobs":
        jobs = list(
            Job.objects.values("id", "title", "description", "required_skills").order_by("-created_at")
        )
        return {"ok": True, "jobs": jobs}

    logger.warning("Unhandled Vapi tool: %s", name)
    return {"ok": False, "message": f"Tool '{name}' not recognized."}


@csrf_exempt
def vapi_hiring_assistant_webhook(request):
    if request.method == "GET":
        return JsonResponse(_build_assistant_payload(), status=200)

    if request.method != "POST":
        return JsonResponse({"detail": "Use GET or POST."}, status=405)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    message = payload.get("message", {})
    message_type = message.get("type", "")

    logger.info("Vapi hiring webhook received: type=%s", message_type)

    if not message_type or message_type == "assistant-request":
        return JsonResponse(_build_assistant_payload(), status=200)

    if message_type == "function-call":
        function_call = message.get("functionCall", {})
        name = function_call.get("name")
        args = _parse_arguments(function_call.get("arguments"))
        result = _execute_tool(name, args)
        return JsonResponse({"result": result}, status=200)

    if message_type == "tool-calls":
        tool_calls = message.get("toolCallList", [])
        results = []
        for call in tool_calls:
            fn_payload = call.get("function", {})
            name = fn_payload.get("name") or call.get("name")
            args = _parse_arguments(
                fn_payload.get("arguments")
                or fn_payload.get("parameters")
                or call.get("arguments")
                or call.get("parameters")
                or {}
            )
            result = _execute_tool(name, args)
            results.append(
                {
                    "toolCallId": call.get("id"),
                    "name": name,
                    "result": json.dumps(result),
                }
            )
        return JsonResponse({"results": results}, status=200)

    if message_type in {"status-update", "end-of-call-report", "hang"}:
        return JsonResponse({"ok": True}, status=200)

    return JsonResponse({"ok": True}, status=200)
