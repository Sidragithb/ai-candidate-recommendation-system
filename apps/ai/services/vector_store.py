import re

from django.conf import settings
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models


class CandidateMatch(BaseModel):
    candidate_id: int
    full_name: str
    score: float
    fit_score: float | None = None
    matched_skills: list[str] = Field(default_factory=list)
    matched_education: list[str] = Field(default_factory=list)
    keyword_matches: list[str] = Field(default_factory=list)
    ranking_reasons: list[str] = Field(default_factory=list)
    semantic_score: float | None = None
    skill_overlap_score: float | None = None
    experience_score: float | None = None
    education_score: float | None = None
    estimated_years_experience: float | None = None
    education_level: str | None = None
    degree_title: str | None = None
    education_institution: str | None = None


class VectorSearchService:
    EDUCATION_LEVEL_ALIASES = {
        "bachelors": "Bachelors",
        "bachelor": "Bachelors",
        "bsc": "Bachelors",
        "bscs": "Bachelors",
        "bs": "Bachelors",
        "bscs": "Bachelors",
        "bsse": "Bachelors",
        "bsit": "Bachelors",
        "masters": "Masters",
        "master": "Masters",
        "msc": "Masters",
        "ms": "Masters",
        "mba": "Masters",
        "phd": "PhD",
        "doctorate": "PhD",
        "hnd": "Bachelors",
    }
    EDUCATION_FIELD_ALIASES = {
        "computer science": "computer science",
        "software engineering": "software engineering",
        "information technology": "information technology",
        "computing": "computing",
        "pre-engineering": "pre-engineering",
    }
    EDUCATION_FIELD_PATTERNS = {
        "computer science": {"computer science", "bscs", "bs computer science", "bsc computer science"},
        "software engineering": {"software engineering", "bsse", "bse"},
        "information technology": {"information technology", "bsit"},
        "computing": {"computing", "hnd computing"},
        "pre-engineering": {"pre-engineering"},
    }

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
        degree_title: str,
        education_institution: str,
        education_score: float,
        fit_score: float,
        fit_breakdown: dict,
        ranking_reasons: list[str],
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
                        "degree_title": degree_title,
                        "education_institution": education_institution,
                        "education_score": education_score,
                        "fit_score": fit_score,
                        "fit_breakdown": fit_breakdown,
                        "ranking_reasons": ranking_reasons,
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
        query_terms = self._extract_query_terms(query_text)
        education_query = self._parse_education_query(query_text)
        is_education_query = self._is_education_specific_query(query_text, education_query)

        if is_education_query:
            return self._search_education_matches(
                client=client,
                job_id=job_id,
                education_query=education_query,
                limit=limit,
            )

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
            limit=self._expanded_fetch_limit(limit, query_text, query_terms, education_query),
            with_payload=True,
        )
        results = response.points
        matches: list[CandidateMatch] = []
        for result in results:
            payload = result.payload or {}
            candidate_skills = [str(skill) for skill in payload.get("skills", [])]
            resume_text = str(payload.get("resume_text", ""))
            effective_education_level = self._resolve_education_level(
                str(payload.get("education_level", "")),
                str(payload.get("degree_title", "")),
            )
            education_details = [
                effective_education_level,
                str(payload.get("degree_title", "")),
                str(payload.get("education_institution", "")),
            ]
            matched_skills = [
                skill for skill in candidate_skills if self._skill_matches_query(skill, query_terms)
            ]
            resume_skill_matches = self._extract_resume_skill_matches(resume_text, query_terms)
            if resume_skill_matches:
                matched_skills = list(dict.fromkeys([*matched_skills, *resume_skill_matches]))
            matched_education = [
                detail for detail in education_details if self._education_matches_query(detail, education_query)
            ]
            semantic_score = round(float(result.score), 4)
            experience_score = round(float(payload.get("experience_score", 0.0)), 4)
            stored_education_score = float(payload.get("education_score", 0.0))
            education_score = round(
                stored_education_score or self._education_score(effective_education_level),
                4,
            )
            ranking_reasons = [str(reason) for reason in payload.get("ranking_reasons", [])]
            skill_overlap_score = round(
                (len(matched_skills) + len(matched_education)) / max(len(query_terms), 1),
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
                    fit_score=float(payload.get("fit_score", 0.0) or 0.0),
                    matched_skills=matched_skills,
                    matched_education=matched_education,
                    keyword_matches=[],
                    ranking_reasons=ranking_reasons,
                    semantic_score=semantic_score,
                    skill_overlap_score=skill_overlap_score,
                    experience_score=experience_score,
                    education_score=education_score,
                    estimated_years_experience=float(payload.get("estimated_years_experience", 0.0)),
                    education_level=effective_education_level,
                    degree_title=str(payload.get("degree_title", "")),
                    education_institution=str(payload.get("education_institution", "")),
                )
            )
        if self._is_strict_match_query(query_text, query_terms):
            strict_skill_matches = [match for match in matches if match.matched_skills]
            if strict_skill_matches:
                matches = strict_skill_matches
        if self._is_education_specific_query(query_text, education_query):
            strict_education_matches = [match for match in matches if match.matched_education]
            if strict_education_matches:
                matches = strict_education_matches
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    def _search_education_matches(
        self,
        client: QdrantClient,
        job_id: int | None,
        education_query: dict,
        limit: int,
    ) -> list[CandidateMatch]:
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

        points, _ = client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            scroll_filter=query_filter,
            limit=200,
            with_payload=True,
            with_vectors=False,
        )

        matches: list[CandidateMatch] = []
        for point in points:
            payload = point.payload or {}
            effective_education_level = self._resolve_education_level(
                str(payload.get("education_level", "")),
                str(payload.get("degree_title", "")),
            )
            education_details = [
                effective_education_level,
                str(payload.get("degree_title", "")),
                str(payload.get("education_institution", "")),
            ]
            matched_education = [
                detail for detail in education_details if self._education_matches_query(detail, education_query)
            ]
            if not matched_education:
                continue

            experience_score = round(float(payload.get("experience_score", 0.0)), 4)
            stored_education_score = float(payload.get("education_score", 0.0))
            education_score = round(
                stored_education_score or self._education_score(effective_education_level),
                4,
            )
            field_match_count = sum(
                1
                for field in education_query.get("fields", set())
                if self._education_field_matches(str(payload.get("degree_title", "")).lower(), field)
                or self._education_field_matches(str(payload.get("education_institution", "")).lower(), field)
            )
            level_match_count = sum(
                1 for level in education_query.get("levels", set()) if level.lower() in effective_education_level.lower()
            )
            combined_score = round(
                min(
                    0.4
                    + (field_match_count * 0.3)
                    + (level_match_count * 0.12)
                    + (education_score * 0.1)
                    + (experience_score * 0.08),
                    1.0,
                ),
                4,
            )
            matches.append(
                CandidateMatch(
                    candidate_id=int(payload.get("candidate_id", point.id)),
                    full_name=str(payload.get("full_name", "Unknown Candidate")),
                    score=combined_score,
                    fit_score=float(payload.get("fit_score", 0.0) or 0.0),
                    matched_skills=[],
                    matched_education=matched_education,
                    keyword_matches=[],
                    ranking_reasons=[str(reason) for reason in payload.get("ranking_reasons", [])],
                    semantic_score=None,
                    skill_overlap_score=0.0,
                    experience_score=experience_score,
                    education_score=education_score,
                    estimated_years_experience=float(payload.get("estimated_years_experience", 0.0)),
                    education_level=effective_education_level,
                    degree_title=str(payload.get("degree_title", "")),
                    education_institution=str(payload.get("education_institution", "")),
                )
            )

        matches.sort(
            key=lambda item: (
                item.score,
                len(item.matched_education),
                item.education_score or 0.0,
                item.experience_score or 0.0,
            ),
            reverse=True,
        )
        return matches[:limit]

    def _expanded_fetch_limit(
        self,
        limit: int,
        query_text: str,
        query_terms: set[str],
        education_query: dict,
    ) -> int:
        if self._is_strict_match_query(query_text, query_terms) or self._is_education_specific_query(
            query_text, education_query
        ):
            return max(limit * 10, 50)
        return limit

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
            "candidates",
            "developer",
            "engineer",
            "to",
            "year",
            "years",
            "experience",
            "in",
            "or",
            "for",
            "the",
            "and",
            "with",
            "who",
            "which",
            "is",
            "has",
            "have",
            "skill",
            "skills",
            "show",
            "from",
            "university",
            "college",
            "institute",
            "institution",
            "studied",
            "degree",
            "bachelor",
            "bachelors",
            "master",
            "masters",
            "phd",
            "science",
            "engineering",
            "computer",
            "software",
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

    def _education_matches_query(self, value: str, education_query: dict) -> bool:
        normalized_value = value.lower().strip()
        if not normalized_value:
            return False

        levels = education_query.get("levels", set())
        fields = education_query.get("fields", set())
        if not levels and not fields:
            return False

        level_match = not levels or any(level.lower() in normalized_value for level in levels)
        field_match = not fields or any(self._education_field_matches(normalized_value, field) for field in fields)
        if fields:
            return field_match
        return level_match and field_match

    def _extract_resume_skill_matches(self, resume_text: str, query_terms: set[str]) -> list[str]:
        normalized_text = f" {resume_text.lower()} "
        matches: list[str] = []
        for term in query_terms:
            normalized_term = term.strip().lower()
            if len(normalized_term) < 2:
                continue
            if f" {normalized_term} " in normalized_text:
                matches.append(normalized_term.title())
        return matches

    def _parse_education_query(self, query_text: str) -> dict:
        lowered = " ".join(query_text.lower().replace("/", " ").replace(",", " ").split())
        levels = {
            canonical
            for token, canonical in self.EDUCATION_LEVEL_ALIASES.items()
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered)
        }
        fields = {
            canonical
            for phrase, canonical in self.EDUCATION_FIELD_ALIASES.items()
            if phrase in lowered
        }
        return {"levels": levels, "fields": fields}

    def _is_strict_match_query(self, query_text: str, query_terms: set[str]) -> bool:
        normalized_query = query_text.lower()
        strict_markers = {
            "skill",
            "skills",
            "have",
            "has",
            "with",
            "knows",
            "know",
            "expert",
            "experience",
        }
        if any(marker in normalized_query.split() for marker in strict_markers):
            return True
        return len(query_terms) <= 3 and len(query_terms) > 0 and any(
            term not in {"senior", "junior", "lead", "backend", "frontend", "fullstack"}
            for term in query_terms
        )

    def _is_education_specific_query(self, query_text: str, education_query: dict) -> bool:
        normalized_query = query_text.lower()
        education_markers = {
            "degree",
            "university",
            "college",
            "institute",
            "institution",
            "graduated",
            "graduate",
            "education",
            "studied",
            "from",
            "bachelor",
            "bachelors",
            "master",
            "masters",
            "phd",
            "computer",
            "software",
            "engineering",
        }
        return any(marker in normalized_query.split() for marker in education_markers) and bool(
            education_query.get("levels") or education_query.get("fields")
        )

    def _resolve_education_level(self, education_level: str, degree_title: str) -> str:
        if education_level.strip():
            return education_level.strip()

        normalized_degree = degree_title.lower()
        if any(token in normalized_degree for token in ["phd", "ph.d", "doctor of philosophy"]):
            return "PhD"
        if any(token in normalized_degree for token in ["master", "msc", "m.s", "mba", "ms "]):
            return "Masters"
        if any(token in normalized_degree for token in ["bachelor", "bsc", "b.s", "bs ", "bscs", "bsse", "bsit"]):
            return "Bachelors"
        if any(token in normalized_degree for token in ["intermediate", "fsc", "a-level"]):
            return "Intermediate"
        return ""

    def _education_score(self, education_level: str) -> float:
        score_map = {
            "PhD": 1.0,
            "Masters": 0.85,
            "Bachelors": 0.7,
            "Intermediate": 0.4,
            "": 0.0,
        }
        return score_map.get(education_level, 0.0)

    def _education_field_matches(self, normalized_value: str, field: str) -> bool:
        patterns = self.EDUCATION_FIELD_PATTERNS.get(field, {field})
        return any(pattern in normalized_value for pattern in patterns)
