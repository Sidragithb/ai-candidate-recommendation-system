import hashlib
import json
import re

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.scoring import FitScoringService
from apps.ai.services.text import split_skills, tokenize_keywords
from apps.ai.services.vector_store import CandidateMatch, VectorSearchService
from apps.candidates.models import Candidate
from apps.jobs.models import Job


class HybridSearchService:
    EDUCATION_FIELD_PATTERNS = {
        "computer science": {"computer science", "bscs", "bs computer science", "bsc computer science"},
        "software engineering": {"software engineering", "bsse", "bse"},
        "information technology": {"information technology", "bsit"},
        "computing": {"computing", "hnd computing"},
        "pre-engineering": {"pre-engineering"},
    }
    COMMON_SKILL_TERMS = {
        "python",
        "django",
        "flask",
        "fastapi",
        "postgresql",
        "sql",
        "rest",
        "rest api",
        "docker",
        "javascript",
        "typescript",
        "react",
        "node.js",
        "mongodb",
        "aws",
        "azure",
        "tensorflow",
        "pytorch",
    }

    def search(self, *, query: str, job: Job | None = None, limit: int = 5) -> list[CandidateMatch]:
        cache_key = self._cache_key(query=query, job_id=job.id if job else None, limit=limit)
        cached = cache.get(cache_key)
        if cached is not None:
            return [CandidateMatch(**item) for item in cached]

        query_embedding = EmbeddingService().embed_text(query)
        education_query = self._parse_education_query(query)
        experience_query = self._parse_experience_query(query)
        semantic_matches = self._semantic_matches(query_embedding=query_embedding, query=query, job=job, limit=limit)
        keyword_rows = self._keyword_matches(query=query, job=job, limit=limit * 3)
        ranked = self._merge_results(
            query,
            query_embedding,
            semantic_matches,
            keyword_rows,
            job,
            limit,
            education_query,
            experience_query,
        )
        cache.set(cache_key, [match.model_dump() for match in ranked], timeout=settings.SEARCH_CACHE_TTL)
        return ranked

    def invalidate_job_cache(self, job_id: int | None) -> None:
        version_key = f"candidate-search-version:{job_id or 'all'}"
        try:
            cache.incr(version_key)
        except Exception:
            cache.set(version_key, 1, None)

    def _semantic_matches(
        self,
        *,
        query_embedding: list[float],
        query: str,
        job: Job | None,
        limit: int,
    ) -> list[CandidateMatch]:
        try:
            return VectorSearchService().search_candidates(
                query_embedding=query_embedding,
                query_text=query,
                job_id=job.id if job else None,
                limit=max(limit * 3, 10),
            )
        except Exception:
            return []

    def _keyword_matches(self, *, query: str, job: Job | None, limit: int) -> list[Candidate]:
        tokens = tokenize_keywords(query)
        filters = Q()
        for token in tokens:
            filters |= Q(skills__icontains=token)
            filters |= Q(resume_text__icontains=token)
            filters |= Q(search_document__icontains=token)
            filters |= Q(degree_title__icontains=token)
            filters |= Q(education_institution__icontains=token)

        queryset = Candidate.objects.select_related("job").filter(processing_status=Candidate.ProcessingStatus.COMPLETED)
        if job is not None:
            queryset = queryset.filter(job=job)
        if filters:
            queryset = queryset.filter(filters)
        return list(queryset.order_by("-fit_score", "-created_at")[:limit])

    def _merge_results(
        self,
        query: str,
        query_embedding: list[float],
        semantic_matches: list[CandidateMatch],
        keyword_rows: list[Candidate],
        job: Job | None,
        limit: int,
        education_query: dict,
        experience_query: dict,
    ) -> list[CandidateMatch]:
        match_by_id: dict[int, CandidateMatch] = {match.candidate_id: match for match in semantic_matches}
        tokens = tokenize_keywords(query)
        education_fields = education_query.get("fields", set())
        education_levels = education_query.get("levels", set())
        requested_skill_terms = self._requested_skill_terms(query=query, job=job, tokens=tokens)
        is_education_query = bool(education_fields or education_levels)
        is_experience_query = experience_query.get("min_years") is not None or experience_query.get("max_years") is not None
        is_mixed_skill_experience_query = is_experience_query and len(requested_skill_terms) >= 2
        is_pure_education_query = is_education_query and not requested_skill_terms and not is_experience_query
        is_pure_experience_query = is_experience_query and not requested_skill_terms and not is_education_query

        for candidate in keyword_rows:
            keyword_hits = self._keyword_hits(
                candidate=candidate,
                tokens=tokens,
                education_query=education_query,
                experience_query=experience_query,
                requested_skill_terms=requested_skill_terms,
                pure_education_only=is_pure_education_query,
                pure_experience_only=is_pure_experience_query,
            )
            if candidate.id not in match_by_id:
                match_by_id[candidate.id] = CandidateMatch(
                    candidate_id=candidate.id,
                    full_name=candidate.full_name,
                    score=0.0,
                    fit_score=float(candidate.fit_score),
                    matched_skills=(
                        []
                        if is_pure_education_query or is_pure_experience_query
                        else self._matched_query_skills(candidate, requested_skill_terms)
                    ),
                    matched_education=self._education_hits(candidate, education_query),
                    keyword_matches=keyword_hits,
                    ranking_reasons=list(candidate.ranking_reasons or []),
                    semantic_score=0.0,
                    skill_overlap_score=0.0,
                    experience_score=float(candidate.experience_score),
                    education_score=float(candidate.education_score),
                    estimated_years_experience=float(candidate.estimated_years_experience),
                    education_level=candidate.education_level,
                    degree_title=candidate.degree_title,
                    education_institution=candidate.education_institution,
                )
            else:
                existing = match_by_id[candidate.id]
                existing.keyword_matches = sorted(set([*existing.keyword_matches, *keyword_hits]))
                if not existing.fit_score:
                    existing.fit_score = float(candidate.fit_score)
                if candidate.ranking_reasons:
                    existing.ranking_reasons = list(dict.fromkeys([*existing.ranking_reasons, *candidate.ranking_reasons]))

        if job is None:
            query_job = self._synthetic_job(query, query_embedding)
        else:
            query_job = job

        for candidate_id, match in list(match_by_id.items()):
            candidate = Candidate.objects.filter(id=candidate_id).first()
            if candidate is None:
                continue
            scoring = FitScoringService().score_candidate_against_job(
                candidate_embedding=candidate.embedding or [],
                candidate_skills=candidate.parsed_skills or split_skills(candidate.skills),
                resume_text=candidate.resume_text,
                candidate_years_experience=float(candidate.estimated_years_experience),
                candidate_education_level=candidate.education_level,
                job_embedding=query_job.embedding if hasattr(query_job, "embedding") else query_embedding,
                job_required_skills=(
                    query_job.normalized_required_skills
                    if hasattr(query_job, "normalized_required_skills")
                    else split_skills(query)
                ),
                job_description=query_job.description if hasattr(query_job, "description") else query,
            )
            keyword_matches = self._keyword_hits(
                candidate=candidate,
                tokens=tokens,
                education_query=education_query,
                experience_query=experience_query,
                requested_skill_terms=requested_skill_terms,
                pure_education_only=is_pure_education_query,
                pure_experience_only=is_pure_experience_query,
            )
            semantic_component = match.semantic_score or scoring["breakdown"]["vector_score"]
            keyword_component = max(scoring["breakdown"]["keyword_score"], len(keyword_matches) / max(len(tokens), 1))
            requested_skill_overlap = self._requested_skill_overlap(candidate, requested_skill_terms)
            skill_component = max(
                scoring["breakdown"]["skill_score"] if not requested_skill_terms else requested_skill_overlap,
                match.skill_overlap_score or 0.0,
            )
            experience_component = scoring["breakdown"]["experience_score"]
            experience_range_score = self._experience_range_score(
                candidate_years=float(candidate.estimated_years_experience),
                experience_query=experience_query,
            )
            score = (
                semantic_component * 0.45
                + keyword_component * 0.25
                + skill_component * 0.15
                + max(experience_component, experience_range_score) * 0.1
                + scoring["breakdown"]["education_score"] * 0.05
            )
            match.keyword_matches = sorted(set([*match.keyword_matches, *keyword_matches]))
            if is_pure_education_query or is_pure_experience_query:
                match.matched_skills = []
            elif requested_skill_terms:
                match.matched_skills = sorted(
                    set([*match.matched_skills, *self._matched_query_skills(candidate, requested_skill_terms)])
                )
            else:
                match.matched_skills = sorted(set([*match.matched_skills, *scoring["matched_skills"]]))
            match.matched_education = sorted(
                set([*match.matched_education, *self._education_hits(candidate, education_query)])
            )
            match.fit_score = scoring["fit_score"]
            if is_pure_education_query:
                match.ranking_reasons = self._education_ranking_reasons(
                    candidate=candidate,
                    education_query=education_query,
                    keyword_matches=keyword_matches,
                    scoring=scoring,
                )
            elif is_pure_experience_query:
                match.ranking_reasons = self._experience_ranking_reasons(
                    candidate=candidate,
                    experience_query=experience_query,
                    keyword_matches=keyword_matches,
                    scoring=scoring,
                )
            elif is_mixed_skill_experience_query:
                match.ranking_reasons = self._mixed_skill_experience_reasons(
                    candidate=candidate,
                    requested_skill_terms=requested_skill_terms,
                    experience_query=experience_query,
                    keyword_matches=keyword_matches,
                    scoring=scoring,
                )
            else:
                match.ranking_reasons = list(dict.fromkeys([*match.ranking_reasons, *scoring["reasons"]]))[:5]
            match.score = round(min(score, 1.0), 4)

        if is_pure_education_query:
            strict_education_matches = [match for match in match_by_id.values() if match.matched_education]
            if strict_education_matches:
                match_by_id = {match.candidate_id: match for match in strict_education_matches}
        elif is_experience_query:
            strict_experience_matches = [
                match
                for match in match_by_id.values()
                if self._experience_hit(
                    candidate_years=float(match.estimated_years_experience or 0.0),
                    experience_query=experience_query,
                )
            ]
            if strict_experience_matches:
                match_by_id = {match.candidate_id: match for match in strict_experience_matches}

        ranked = sorted(
            match_by_id.values(),
            key=lambda item: (
                self._requested_skill_sort_score(item, requested_skill_terms),
                self._experience_range_score(
                    candidate_years=float(item.estimated_years_experience or 0.0),
                    experience_query=experience_query,
                ),
                item.score,
                item.fit_score or 0.0,
                item.semantic_score or 0.0,
            ),
            reverse=True,
        )
        return ranked[:limit]

    def _synthetic_job(self, query: str, query_embedding: list[float]):
        return type(
            "SyntheticJob",
            (),
            {
                "id": None,
                "title": query,
                "description": query,
                "embedding": query_embedding,
                "normalized_required_skills": split_skills(query),
            },
        )()

    def _cache_key(self, *, query: str, job_id: int | None, limit: int) -> str:
        version = cache.get(f"candidate-search-version:{job_id or 'all'}", 1)
        digest = hashlib.sha256(json.dumps({"query": query, "job_id": job_id, "limit": limit}).encode("utf-8")).hexdigest()
        return f"candidate-search:{job_id or 'all'}:{version}:{digest}"

    def _parse_education_query(self, query: str) -> dict:
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

    def _parse_experience_query(self, query: str) -> dict:
        lowered = " ".join(query.lower().split())
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s+years?", lowered)
        if match:
            minimum = float(match.group(1))
            maximum = float(match.group(2))
            return {"min_years": min(minimum, maximum), "max_years": max(minimum, maximum)}

        at_least_match = re.search(r"(\d+(?:\.\d+)?)\+?\s+years?", lowered)
        if at_least_match and "experience" in lowered:
            value = float(at_least_match.group(1))
            return {"min_years": value, "max_years": None}
        return {"min_years": None, "max_years": None}

    def _education_hits(self, candidate: Candidate, education_query: dict) -> list[str]:
        hits: list[str] = []
        levels = education_query.get("levels", set())
        fields = education_query.get("fields", set())
        degree = (candidate.degree_title or "").strip()
        institution = (candidate.education_institution or "").strip()
        lowered_degree = degree.lower()
        lowered_institution = institution.lower()
        field_hit = False
        for field in fields:
            if self._education_field_matches(lowered_degree, field) and degree:
                hits.append(degree)
                field_hit = True
                break
            if self._education_field_matches(lowered_institution, field) and institution:
                hits.append(institution)
                field_hit = True
                break
        if levels and candidate.education_level in levels and (not fields or field_hit):
            hits.insert(0, candidate.education_level)
        return hits

    def _keyword_hits(
        self,
        *,
        candidate: Candidate,
        tokens: list[str],
        education_query: dict,
        experience_query: dict,
        requested_skill_terms: set[str],
        pure_education_only: bool,
        pure_experience_only: bool,
    ) -> list[str]:
        if pure_education_only:
            education_hits = self._education_hits(candidate, education_query)
            return education_hits
        if pure_experience_only:
            experience_hit = self._experience_hit(float(candidate.estimated_years_experience), experience_query)
            return [experience_hit] if experience_hit else []
        hits = [token for token in tokens if token in candidate.search_document.lower()]
        if requested_skill_terms:
            hits.extend(self._matched_query_skills(candidate, requested_skill_terms))
        if education_query.get("fields") or education_query.get("levels"):
            hits.extend(self._education_hits(candidate, education_query))
        if experience_query.get("min_years") is not None or experience_query.get("max_years") is not None:
            experience_hit = self._experience_hit(float(candidate.estimated_years_experience), experience_query)
            if experience_hit:
                hits.append(experience_hit)
        return sorted(dict.fromkeys(hits))

    def _education_ranking_reasons(
        self,
        *,
        candidate: Candidate,
        education_query: dict,
        keyword_matches: list[str],
        scoring: dict,
    ) -> list[str]:
        reasons: list[str] = []
        education_hits = self._education_hits(candidate, education_query)
        if education_hits:
            reasons.append(f"Matched requested education: {', '.join(education_hits[:3])}.")
        if keyword_matches:
            reasons.append(f"Education evidence found: {', '.join(keyword_matches[:3])}.")
        if candidate.education_level:
            reasons.append(f"Education level detected: {candidate.education_level}.")
        if float(candidate.estimated_years_experience or 0.0):
            reasons.append(f"Estimated experience is {float(candidate.estimated_years_experience):.1f} years.")
        missing_fields = sorted(
            field
            for field in education_query.get("fields", set())
            if field not in (candidate.degree_title or "").lower()
            and field not in (candidate.education_institution or "").lower()
        )
        if missing_fields:
            reasons.append(f"Missing or unclear education fields: {', '.join(missing_fields[:3])}.")
        if not reasons:
            reasons.extend(scoring.get("reasons", [])[:3])
        return reasons[:5]

    def _experience_ranking_reasons(
        self,
        *,
        candidate: Candidate,
        experience_query: dict,
        keyword_matches: list[str],
        scoring: dict,
    ) -> list[str]:
        reasons: list[str] = []
        experience_hit = self._experience_hit(float(candidate.estimated_years_experience), experience_query)
        if experience_hit:
            reasons.append(f"Matched requested experience range: {experience_hit}.")
        if keyword_matches:
            reasons.append(f"Experience evidence found: {', '.join(keyword_matches[:2])}.")
        if candidate.parsed_skills:
            reasons.append(f"Relevant skills include: {', '.join(candidate.parsed_skills[:4])}.")
        if candidate.education_level:
            reasons.append(f"Education level detected: {candidate.education_level}.")
        if not reasons:
            reasons.extend(scoring.get("reasons", [])[:3])
        return reasons[:5]

    def _mixed_skill_experience_reasons(
        self,
        *,
        candidate: Candidate,
        requested_skill_terms: set[str],
        experience_query: dict,
        keyword_matches: list[str],
        scoring: dict,
    ) -> list[str]:
        reasons: list[str] = []
        matched_skills = self._matched_query_skills(candidate, requested_skill_terms)
        if matched_skills:
            reasons.append(f"Matched requested skills: {', '.join(matched_skills[:4])}.")
        experience_hit = self._experience_hit(float(candidate.estimated_years_experience), experience_query)
        if experience_hit:
            reasons.append(f"Matched requested experience range: {experience_hit}.")
        elif float(candidate.estimated_years_experience or 0.0):
            reasons.append(f"Estimated experience is {float(candidate.estimated_years_experience):.1f} years.")
        if keyword_matches:
            reasons.append(f"Search evidence found: {', '.join(keyword_matches[:4])}.")
        missing_skills = sorted(skill for skill in requested_skill_terms if skill not in {s.lower() for s in candidate.parsed_skills})
        if missing_skills:
            reasons.append(f"Missing or unclear requested skills: {', '.join(missing_skills[:3])}.")
        if not reasons:
            reasons.extend(scoring.get("reasons", [])[:3])
        return reasons[:5]

    def _education_field_matches(self, normalized_value: str, field: str) -> bool:
        patterns = self.EDUCATION_FIELD_PATTERNS.get(field, {field})
        return any(pattern in normalized_value for pattern in patterns)

    def _requested_skill_terms(self, *, query: str, job: Job | None, tokens: list[str]) -> set[str]:
        lowered = query.lower()
        candidate_terms = set(self.COMMON_SKILL_TERMS)
        if job is not None:
            candidate_terms.update(skill.lower() for skill in (job.normalized_required_skills or []))
        requested: set[str] = set()
        token_set = set(tokens)
        for term in candidate_terms:
            term_tokens = {part for part in re.split(r"[\s/+-]+", term) if part and part != "."}
            if term in lowered or (term_tokens and term_tokens.issubset(token_set)):
                requested.add(term)
        return requested

    def _matched_query_skills(self, candidate: Candidate, requested_skill_terms: set[str]) -> list[str]:
        if not requested_skill_terms:
            return []
        matched = [
            skill
            for skill in candidate.parsed_skills
            if skill.lower() in requested_skill_terms
        ]
        return sorted(dict.fromkeys(matched))

    def _requested_skill_overlap(self, candidate: Candidate, requested_skill_terms: set[str]) -> float:
        if not requested_skill_terms:
            return 0.0
        matched = len(self._matched_query_skills(candidate, requested_skill_terms))
        return round(matched / max(len(requested_skill_terms), 1), 4)

    def _requested_skill_sort_score(self, match: CandidateMatch, requested_skill_terms: set[str]) -> float:
        if not requested_skill_terms:
            return 0.0
        return round(len(match.matched_skills) / max(len(requested_skill_terms), 1), 4)

    def _experience_range_score(self, *, candidate_years: float, experience_query: dict) -> float:
        minimum = experience_query.get("min_years")
        maximum = experience_query.get("max_years")
        if minimum is None and maximum is None:
            return 0.0
        if minimum is not None and maximum is not None:
            if minimum <= candidate_years <= maximum:
                return 1.0
            distance = min(abs(candidate_years - minimum), abs(candidate_years - maximum))
            return max(0.0, round(1.0 - (distance / max(maximum - minimum, 1.0)), 4))
        if minimum is not None:
            if candidate_years >= minimum:
                return 1.0
            return max(0.0, round(candidate_years / max(minimum, 1.0), 4))
        return 0.0

    def _experience_hit(self, candidate_years: float, experience_query: dict) -> str:
        minimum = experience_query.get("min_years")
        maximum = experience_query.get("max_years")
        if minimum is None and maximum is None:
            return ""
        if minimum is not None and maximum is not None and minimum <= candidate_years <= maximum:
            return f"{candidate_years:.1f} years"
        if minimum is not None and maximum is None and candidate_years >= minimum:
            return f"{candidate_years:.1f} years"
        return ""
