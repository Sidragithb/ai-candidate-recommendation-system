from math import sqrt

from django.conf import settings

from apps.ai.services.text import education_score, experience_score, split_skills, tokenize_keywords


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(min(numerator / (left_norm * right_norm), 1.0), -1.0)


class FitScoringService:
    def score_candidate_against_job(
        self,
        *,
        candidate_embedding: list[float],
        candidate_skills: list[str],
        resume_text: str,
        candidate_years_experience: float,
        candidate_education_level: str,
        job_embedding: list[float],
        job_required_skills: list[str],
        job_description: str,
    ) -> dict:
        normalized_candidate_skills = {skill.lower() for skill in split_skills(candidate_skills)}
        normalized_job_skills = {skill.lower() for skill in split_skills(job_required_skills)}
        matched_skills = sorted(skill for skill in normalized_job_skills if skill in normalized_candidate_skills)
        missing_skills = sorted(skill for skill in normalized_job_skills if skill not in normalized_candidate_skills)

        keyword_terms = set(tokenize_keywords(job_description))
        text_blob = f"{' '.join(candidate_skills)} {resume_text}".lower()
        keyword_hits = sorted(term for term in keyword_terms if term in text_blob)

        vector_score = max((cosine_similarity(candidate_embedding, job_embedding) + 1.0) / 2.0, 0.0)
        keyword_score = min(len(keyword_hits) / max(len(keyword_terms), 1), 1.0)
        skill_score = min(len(matched_skills) / max(len(normalized_job_skills), 1), 1.0)
        exp_score = experience_score(candidate_years_experience)
        edu_score = education_score(candidate_education_level)

        final_score = (
            vector_score * settings.SEARCH_VECTOR_WEIGHT
            + keyword_score * settings.SEARCH_KEYWORD_WEIGHT
            + skill_score * settings.SEARCH_SKILL_WEIGHT
            + exp_score * settings.SEARCH_EXPERIENCE_WEIGHT
            + edu_score * settings.SEARCH_EDUCATION_WEIGHT
        )
        percentage = round(final_score * 100.0, 2)

        reasons: list[str] = []
        if matched_skills:
            reasons.append(f"Matched required skills: {', '.join(matched_skills[:5])}.")
        if keyword_hits:
            reasons.append(f"Resume aligns with job keywords: {', '.join(keyword_hits[:6])}.")
        if candidate_years_experience:
            reasons.append(f"Estimated experience is {candidate_years_experience:.1f} years.")
        if candidate_education_level:
            reasons.append(f"Education signal detected: {candidate_education_level}.")
        if missing_skills:
            reasons.append(f"Missing or unclear skills: {', '.join(missing_skills[:4])}.")

        return {
            "fit_score": percentage,
            "breakdown": {
                "vector_score": round(vector_score, 4),
                "keyword_score": round(keyword_score, 4),
                "skill_score": round(skill_score, 4),
                "experience_score": round(exp_score, 4),
                "education_score": round(edu_score, 4),
            },
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "keyword_hits": keyword_hits[:10],
            "reasons": reasons[:5],
        }
