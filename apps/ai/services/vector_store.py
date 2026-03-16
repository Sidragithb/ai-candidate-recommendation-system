from django.conf import settings
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models


class CandidateMatch(BaseModel):
    candidate_id: int
    full_name: str
    score: float
    matched_skills: list[str] = Field(default_factory=list)
    semantic_score: float | None = None
    skill_overlap_score: float | None = None
    experience_score: float | None = None
    education_score: float | None = None
    estimated_years_experience: float | None = None
    education_level: str | None = None


class VectorSearchService:
    def __init__(self) -> None:
        self._client: QdrantClient | None = None

    def index_candidate(
        self,
        candidate_id: int,
        job_id: int,
        full_name: str,
        email: str,
        skills: list[str],
        resume_text: str,
        years_experience: float,
        experience_score: float,
        education_level: str,
        education_score: float,
        embedding: list[float],
    ) -> None:
        client = self._get_client()
        self._ensure_collection(client)
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            wait=True,
            points=[
                models.PointStruct(
                    id=candidate_id,
                    vector=embedding,
                    payload={
                        "candidate_id": candidate_id,
                        "job_id": job_id,
                        "full_name": full_name,
                        "email": email,
                        "skills": skills,
                        "resume_text": resume_text,
                        "estimated_years_experience": years_experience,
                        "experience_score": experience_score,
                        "education_level": education_level,
                        "education_score": education_score,
                    },
                )
            ],
        )

    def search_candidates(
        self,
        query_embedding: list[float],
        query_text: str = "",
        job_id: int | None = None,
        limit: int = 5,
    ) -> list[CandidateMatch]:
        client = self._get_client()
        self._ensure_collection(client)

        query_filter = None
        if job_id is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="job_id",
                        match=models.MatchValue(value=job_id),
                    )
                ]
            )

        response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_embedding,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        results = response.points
        matches: list[CandidateMatch] = []
        query_terms = self._extract_query_terms(query_text)
        for result in results:
            payload = result.payload or {}
            candidate_skills = [str(skill) for skill in payload.get("skills", [])]
            matched_skills = [
                skill for skill in candidate_skills if self._skill_matches_query(skill, query_terms)
            ]
            semantic_score = round(float(result.score), 4)
            experience_score = round(float(payload.get("experience_score", 0.0)), 4)
            education_score = round(float(payload.get("education_score", 0.0)), 4)
            skill_overlap_score = round(
                len(matched_skills) / max(len(query_terms), 1),
                4,
            )
            combined_score = round(
                min(
                    semantic_score
                    + (skill_overlap_score * 0.35)
                    + (experience_score * 0.12)
                    + (education_score * 0.08),
                    1.0,
                ),
                4,
            )
            matches.append(
                CandidateMatch(
                    candidate_id=int(payload.get("candidate_id", result.id)),
                    full_name=str(payload.get("full_name", "Unknown Candidate")),
                    score=combined_score,
                    matched_skills=matched_skills,
                    semantic_score=semantic_score,
                    skill_overlap_score=skill_overlap_score,
                    experience_score=experience_score,
                    education_score=education_score,
                    estimated_years_experience=float(payload.get("estimated_years_experience", 0.0)),
                    education_level=str(payload.get("education_level", "")),
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=settings.QDRANT_URL)
        return self._client

    def _ensure_collection(self, client: QdrantClient) -> None:
        if client.collection_exists(settings.QDRANT_COLLECTION):
            return

        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )

    def _extract_query_terms(self, query_text: str) -> set[str]:
        stop_words = {
            "best",
            "candidate",
            "developer",
            "engineer",
            "for",
            "the",
            "and",
            "with",
            "who",
            "is",
        }
        cleaned = query_text.replace(",", " ").replace("/", " ").lower()
        return {
            token.strip()
            for token in cleaned.split()
            if token.strip() and token.strip() not in stop_words
        }

    def _skill_matches_query(self, skill: str, query_terms: set[str]) -> bool:
        normalized_skill = skill.lower().strip()
        if not query_terms:
            return False
        if normalized_skill in query_terms:
            return True
        return any(term in normalized_skill or normalized_skill in term for term in query_terms)
