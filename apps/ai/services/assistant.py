import httpx
from django.conf import settings

from apps.ai.services.vector_store import CandidateMatch


class AssistantResponseService:
    """Builds recruiter-friendly answers from retrieved candidate matches."""

    def build_response(
        self,
        query: str,
        matches: list[CandidateMatch],
        job_id: int | None = None,
    ) -> dict:
        summary = self._build_summary(query=query, matches=matches, job_id=job_id)

        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                answer = self._generate_with_openai(query=query, matches=matches, job_id=job_id)
            except Exception:
                answer = self._generate_placeholder_answer(query=query, matches=matches)
        else:
            answer = self._generate_placeholder_answer(query=query, matches=matches)

        return {
            "answer": answer,
            "summary": summary,
            "provider": self.provider,
            "model": self.model,
        }

    def _build_summary(
        self,
        query: str,
        matches: list[CandidateMatch],
        job_id: int | None,
    ) -> dict:
        if not matches:
            return {
                "query": query,
                "job_id": job_id,
                "total_matches": 0,
                "top_candidate": None,
            }

        top_candidate = matches[0]
        return {
            "query": query,
            "job_id": job_id,
            "total_matches": len(matches),
            "top_candidate": {
                "candidate_id": top_candidate.candidate_id,
                "full_name": top_candidate.full_name,
                "score": top_candidate.score,
            },
        }

    def _generate_placeholder_answer(self, query: str, matches: list[CandidateMatch]) -> str:
        if not matches:
            return "No relevant candidates were found for this query."

        top_candidate = matches[0]
        lines = [
            f"Best match for '{query}' is {top_candidate.full_name} with a score of {top_candidate.score:.2f}.",
        ]

        if top_candidate.matched_skills:
            lines.append("Top matched skills: " + ", ".join(top_candidate.matched_skills) + ".")

        if len(matches) > 1:
            lines.append(
                "Other relevant candidates: "
                + ", ".join(f"{match.full_name} ({match.score:.2f})" for match in matches[1:4])
                + "."
            )

        return " ".join(lines)

    def _generate_with_openai(
        self,
        query: str,
        matches: list[CandidateMatch],
        job_id: int | None,
    ) -> str:
        formatted_matches = []
        for match in matches[:5]:
            formatted_matches.append(
                {
                    "candidate_id": match.candidate_id,
                    "full_name": match.full_name,
                    "score": match.score,
                    "matched_skills": match.matched_skills,
                    "semantic_score": match.semantic_score,
                    "skill_overlap_score": match.skill_overlap_score,
                    "estimated_years_experience": match.estimated_years_experience,
                    "experience_score": match.experience_score,
                    "education_level": match.education_level,
                    "education_score": match.education_score,
                }
            )

        system_prompt = (
            "You are an AI hiring assistant for recruiters. Use only the provided candidate search results. "
            "Prioritize exact skill relevance first, then semantic score, then experience and education signals. "
            "Keep the answer short and direct. State the best candidate clearly, explain the strongest matching skills, "
            "and mention alternatives only if the recruiter explicitly asked for top candidates or comparison. "
            "If candidates are close, say that explicitly. Do not invent candidates, skills, education, experience, or scores. "
            "Do not add generic next steps, menus, or repeated offers for more help."
        )

        user_prompt = {
            "query": query,
            "job_id": job_id,
            "matches": formatted_matches,
        }

        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ASSISTANT_MODEL,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": str(user_prompt)}],
                    },
                ],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        payload = response.json()
        output = payload.get("output", [])
        texts: list[str] = []
        for item in output:
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    texts.append(text)
        if texts:
            return " ".join(texts).strip()
        return self._generate_placeholder_answer(query=query, matches=matches)

    @property
    def provider(self) -> str:
        return settings.ASSISTANT_PROVIDER.lower()

    @property
    def model(self) -> str:
        return settings.ASSISTANT_MODEL
