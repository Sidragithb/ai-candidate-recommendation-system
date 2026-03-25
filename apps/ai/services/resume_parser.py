import json
import re

import httpx
from django.conf import settings

from apps.ai.services.text import (
    education_score,
    experience_score,
    extract_years_experience,
    infer_education_level,
    keyword_frequency,
    normalize_whitespace,
    split_skills,
    truncate_text,
)


class ResumeParsingService:
    SECTION_HEADERS = {
        "experience",
        "work experience",
        "employment",
        "projects",
        "project",
        "skills",
        "technical skills",
        "certifications",
        "certification",
        "summary",
        "profile",
        "achievements",
        "activities",
    }
    SKILL_ALIASES = {
        "python": "Python",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "java": "Java",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "react": "React",
        "react.js": "React",
        "reactjs": "React",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "angular": "Angular",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "express": "Express.js",
        "express.js": "Express.js",
        "html": "HTML",
        "css": "CSS",
        "tailwind": "Tailwind CSS",
        "tailwind css": "Tailwind CSS",
        "bootstrap": "Bootstrap",
        "sql": "SQL",
        "mysql": "MySQL",
        "postgresql": "PostgreSQL",
        "mongodb": "MongoDB",
        "firebase": "Firebase",
        "rest": "REST",
        "rest api": "REST API",
        "rest apis": "REST API",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "aws": "AWS",
        "azure": "Azure",
        "mern": "MERN",
        ".net": ".NET",
        "c#": "C#",
        "openai api": "OpenAI API",
        "openai": "OpenAI",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "bert": "BERT",
        "nlp": "NLP",
        "llm": "LLM",
        "machine learning": "Machine Learning",
        "deep learning": "Deep Learning",
        "data analysis": "Data Analysis",
        "computer vision": "Computer Vision",
        "django rest framework": "Django REST Framework",
        "drf": "Django REST Framework",
        "jwt": "JWT",
        "git": "Git",
        "opencv": "OpenCV",
        "spring boot": "Spring Boot",
        "laravel": "Laravel",
        "php": "PHP",
    }
    NON_SKILL_TERMS = {
        "skills",
        "experience",
        "education",
        "lahore",
        "pakistan",
        "university",
        "college",
        "science",
        "software",
        "developer",
        "development",
        "frontend",
        "backend",
        "application",
        "applications",
        "system",
        "project",
        "projects",
        "team",
        "worked",
        "using",
        "built",
        "developed",
        "designed",
        "implemented",
        "integrated",
        "managed",
        "engineering",
        "engineer",
        "tech",
        "stack",
        "response",
        "provide",
        "relevant",
        "learning",
        "training",
        "medical",
        "basic",
        "multiple",
        "tools",
        "data",
        "text",
        "image",
        "web",
        "platform",
        "platforms",
        "services",
        "service",
        "performance",
        "ui",
    }

    def parse_resume(self, resume_text: str, hinted_skills: list[str] | None = None) -> dict:
        normalized_text = (resume_text or "").strip()
        hinted_skills = self.sanitize_skills(hinted_skills or [])
        if not normalized_text:
            return self._empty_result()

        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                return self._parse_with_openai(normalized_text, hinted_skills)
            except Exception:
                pass
        return self._parse_with_heuristics(normalized_text, hinted_skills)

    def _parse_with_heuristics(self, resume_text: str, hinted_skills: list[str]) -> dict:
        lines = self._normalized_lines(resume_text)
        degree_title, institution = self._extract_education_details(lines)
        education_level = infer_education_level(degree_title) or infer_education_level(" ".join(self._extract_education_section(lines)))
        derived_skills = self._extract_skill_candidates(resume_text)
        merged_skills = self.sanitize_skills([*hinted_skills, *derived_skills])
        years_experience = extract_years_experience(resume_text)
        if self._should_use_openai_education_fallback(
            degree_title=degree_title,
            institution=institution,
            resume_text=resume_text,
        ):
            openai_education = self._extract_structured_education_with_openai(resume_text)
            degree_title = openai_education.get("degree_title") or degree_title
            institution = openai_education.get("education_institution") or institution
            education_level = openai_education.get("education_level") or education_level
        return {
            "skills": merged_skills,
            "education_level": education_level,
            "degree_title": truncate_text(degree_title, 255),
            "education_institution": truncate_text(institution, 255),
            "estimated_years_experience": years_experience,
            "experience_score": experience_score(years_experience),
            "education_score": education_score(education_level),
            "confidence": 0.62,
            "source": "heuristic",
        }

    def _parse_with_openai(self, resume_text: str, hinted_skills: list[str]) -> dict:
        system_prompt = (
            "Extract resume data as strict JSON with keys: "
            "skills, education_level, degree_title, education_institution, estimated_years_experience, confidence. "
            "Skills must be a short list of concrete tools, languages, and frameworks. "
            "Use only information present in the resume. Return valid JSON only."
        )
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.RESUME_PARSER_MODEL,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(
                                    {
                                        "hinted_skills": hinted_skills,
                                        "resume_text": resume_text[:16000],
                                    }
                                ),
                            }
                        ],
                    },
                ],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        payload = response.json()
        text_chunks: list[str] = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    text_chunks.append(text)
        result = json.loads("".join(text_chunks).strip())
        skills = self.sanitize_skills(result.get("skills", []))
        education_level = infer_education_level(
            f"{result.get('education_level', '')} {result.get('degree_title', '')}"
        )
        degree_title = str(result.get("degree_title", ""))
        education_institution = str(result.get("education_institution", ""))
        if self._should_use_openai_education_fallback(
            degree_title=degree_title,
            institution=education_institution,
            resume_text=resume_text,
        ):
            structured_education = self._extract_structured_education_with_openai(resume_text)
            degree_title = structured_education.get("degree_title") or degree_title
            education_institution = structured_education.get("education_institution") or education_institution
            education_level = structured_education.get("education_level") or education_level
        years_experience = float(result.get("estimated_years_experience") or 0.0)
        return {
            "skills": skills,
            "education_level": education_level,
            "degree_title": truncate_text(degree_title, 255),
            "education_institution": truncate_text(education_institution, 255),
            "estimated_years_experience": years_experience,
            "experience_score": experience_score(years_experience),
            "education_score": education_score(education_level),
            "confidence": float(result.get("confidence") or 0.75),
            "source": "openai",
        }

    def _extract_skill_candidates(self, resume_text: str) -> list[str]:
        lowered = resume_text.lower()
        matches: list[str] = []
        for alias, canonical in self.SKILL_ALIASES.items():
            pattern = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
            if re.search(pattern, lowered):
                matches.append(canonical)

        skill_section_lines = self._extract_skill_section_lines(resume_text)
        for line in skill_section_lines:
            parts = re.split(r"[,|•;/]", line)
            for part in parts:
                canonical = self._canonicalize_skill(part)
                if canonical:
                    matches.append(canonical)

        frequency = keyword_frequency(resume_text)
        for token, count in frequency.items():
            if count < 2:
                continue
            canonical = self._canonicalize_skill(token)
            if canonical:
                matches.append(canonical)

        return self.sanitize_skills(matches)

    def _extract_skill_section_lines(self, resume_text: str) -> list[str]:
        lines = self._normalized_lines(resume_text)
        selected: list[str] = []
        for index, line in enumerate(lines):
            lowered = line.lower()
            if lowered in {"skills", "technical skills", "tech stack", "technologies", "core skills"}:
                selected.extend(lines[index + 1 : index + 4])
            elif lowered.startswith("skills:") or lowered.startswith("technical skills:"):
                selected.append(line.split(":", 1)[1].strip())
        return selected

    def sanitize_skills(self, raw_skills: list[str] | str) -> list[str]:
        cleaned: list[str] = []
        for item in split_skills(raw_skills):
            canonical = self._canonicalize_skill(item)
            if canonical:
                cleaned.append(canonical)
        return split_skills(cleaned)

    def _canonicalize_skill(self, value: str) -> str:
        candidate = normalize_whitespace(value).strip(" -.:")
        if not candidate:
            return ""
        lowered = candidate.lower()
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = lowered.replace("restful api", "rest api").replace("restful apis", "rest api")
        lowered = lowered.replace("react js", "react.js").replace("reactjs", "react.js")
        lowered = lowered.replace("nextjs", "next.js").replace("nodejs", "node.js")

        if lowered in self.NON_SKILL_TERMS:
            return ""
        if lowered.isdigit() or re.fullmatch(r"\d{2,4}", lowered):
            return ""
        if re.search(r"\b(19|20)\d{2}\b", lowered):
            return ""
        if len(lowered) <= 2 and lowered not in {"c#", ".net", "ai", "ml"}:
            return ""

        if lowered in self.SKILL_ALIASES:
            return self.SKILL_ALIASES[lowered]

        for alias, canonical in self.SKILL_ALIASES.items():
            if lowered == alias:
                return canonical

        return ""

    def _extract_education_details(self, lines: list[str]) -> tuple[str, str]:
        degree_title = ""
        institution = ""
        education_section = self._extract_education_section(lines)
        candidate_lines = education_section or lines[:12]
        if any(line.lower().strip(":") == "education" for line in lines) and not education_section:
            return "", ""
        for index, line in enumerate(candidate_lines):
            normalized = line.lower()
            inline_degree, inline_institution = self._extract_combined_education_line(line)
            if inline_degree and not degree_title:
                degree_title = inline_degree
            if inline_institution and not institution:
                institution = inline_institution
            if self._looks_like_degree_line(normalized):
                cleaned_degree = self._clean_degree_title(line)
                if cleaned_degree and not degree_title:
                    degree_title = cleaned_degree
                if index + 1 < len(candidate_lines) and not institution:
                    institution_candidate = self._clean_institution(candidate_lines[index + 1])
                    if institution_candidate:
                        institution = institution_candidate
            if not institution and self._looks_like_institution_line(normalized):
                institution_candidate = self._clean_institution(line)
                if institution_candidate:
                    institution = institution_candidate
            if degree_title and institution:
                break

        if not degree_title:
            for line in candidate_lines:
                cleaned_degree = self._clean_degree_title(line)
                if cleaned_degree:
                    degree_title = cleaned_degree
                    break
        if not institution:
            for line in candidate_lines:
                institution_candidate = self._clean_institution(line)
                if institution_candidate:
                    institution = institution_candidate
                    break
        return degree_title, institution

    def _normalized_lines(self, resume_text: str) -> list[str]:
        lines = []
        for raw_line in (resume_text or "").splitlines():
            cleaned = normalize_whitespace(
                raw_line.replace("\ufb01", "fi").replace("\ufb02", "fl").replace("â€¢", " ").replace("•", " ")
            )
            cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
            cleaned = cleaned.strip(" -|\t")
            if cleaned:
                lines.append(cleaned)
        return lines

    def _extract_education_section(self, lines: list[str]) -> list[str]:
        start_index = None
        for index, line in enumerate(lines):
            normalized = line.lower().strip(":")
            if normalized == "education" or normalized.startswith("education "):
                start_index = index + 1
                break
        if start_index is None:
            for index, line in enumerate(lines):
                normalized = line.lower().strip(":")
                if normalized == "academic qualification":
                    return lines[max(0, index - 3) : index]
            return []

        section: list[str] = []
        for line in lines[start_index:]:
            normalized = line.lower().strip(":")
            if normalized in self.SECTION_HEADERS:
                break
            if normalized.isupper() and normalized.lower() in self.SECTION_HEADERS:
                break
            section.append(line)
            if len(section) >= 10:
                break
        return section

    def _looks_like_degree_line(self, normalized_line: str) -> bool:
        degree_patterns = [
            r"\bbachelor\b",
            r"\bmaster\b",
            r"\bphd\b",
            r"\bdoctor of philosophy\b",
            r"\bbsc\b",
            r"\bbs(?:cs|se|it)?\b",
            r"\bb\.s\.?\b",
            r"\bmsc\b",
            r"\bm\.s\.?\b",
            r"\bmba\b",
            r"\bhnd\b",
        ]
        if any(re.search(pattern, normalized_line) for pattern in degree_patterns):
            return True
        return False

    def _looks_like_institution_line(self, normalized_line: str) -> bool:
        institution_markers = ("university", "college", "institute", "school", "nuces", "comsats", "bahria", "pearson", "nicon", "ucp")
        if any(marker in normalized_line for marker in institution_markers):
            return True
        return "fast nuces" in normalized_line

    def _clean_degree_title(self, value: str) -> str:
        cleaned = normalize_whitespace(value)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        if lowered in self.SECTION_HEADERS:
            return ""
        if not self._looks_like_degree_line(lowered):
            return ""

        extracted_degree = self._extract_degree_phrase(cleaned)
        if extracted_degree:
            cleaned = extracted_degree
        cleaned = re.split(r"\b(intermediate|matric|pre-engineering)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.sub(r"\b(gpa|cgpa)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(final year project|relevant coursework|coursework|project)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(19|20)\d{2}(?:\s*[-–]\s*(19|20)\d{2})?\b", "", cleaned)
        cleaned = normalize_whitespace(cleaned.strip(" -|,.;"))
        return truncate_text(cleaned, 255)

    def _clean_institution(self, value: str) -> str:
        cleaned = normalize_whitespace(value)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        if lowered in self.SECTION_HEADERS:
            return ""
        if not self._looks_like_institution_line(lowered):
            return ""

        cleaned = re.sub(
            r"^(Bachelor(?:s)?(?: in| of)? [A-Za-z ]+|BS(?:CS|SE|IT)?|BSc\.? [A-Za-z ]+|HND [A-Za-z()& ]+)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b(gpa|cgpa)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(final year project|relevant coursework|coursework|project)\b.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(19|20)\d{2}(?:\s*[-–]\s*(19|20)\d{2})?\b", "", cleaned)
        first_institution = self._extract_first_institution_phrase(cleaned)
        if first_institution:
            cleaned = first_institution
        if "FAST NUCES" in cleaned.upper():
            cleaned = "FAST NUCES"
        cleaned = re.sub(r"\|\s*$", "", cleaned)
        cleaned = re.sub(r"[—-]\s*$", "", cleaned)
        cleaned = normalize_whitespace(cleaned.strip(" -|,.;"))
        return truncate_text(cleaned, 255)

    def _extract_combined_education_line(self, line: str) -> tuple[str, str]:
        cleaned = normalize_whitespace(line)
        lowered = cleaned.lower()
        if not self._looks_like_degree_line(lowered):
            return "", ""

        degree = self._clean_degree_title(cleaned)
        institution = ""

        if not degree:
            degree = self._extract_degree_phrase(cleaned)

        remainder = cleaned
        if degree:
            remainder = normalize_whitespace(re.sub(re.escape(degree), "", cleaned, count=1, flags=re.IGNORECASE))

        if re.search(r"\bbs(?:cs|se|it)?\b", lowered):
            split_match = re.search(r"\bbs(?:cs|se|it)?\b", cleaned, re.IGNORECASE)
            prefix = cleaned[: split_match.start()] if split_match else ""
            suffix = cleaned[split_match.end() :] if split_match else ""
            if prefix.strip() and self._looks_like_institution_line(prefix.lower()):
                institution = self._clean_institution(prefix)
            elif suffix.strip() and self._looks_like_institution_line(suffix.lower()):
                institution = self._clean_institution(suffix)

        first_institution = self._extract_first_institution_phrase(remainder or cleaned)
        if first_institution:
            institution = self._clean_institution(first_institution)
        elif "FAST NUCES" in cleaned.upper():
            institution = "FAST NUCES"

        return degree, institution

    def _extract_degree_phrase(self, cleaned: str) -> str:
        patterns = [
            r"(Bachelor(?:s)?(?: in| of)? [A-Za-z ]{2,80})",
            r"(BSc\.? [A-Za-z ]{2,80})",
            r"(BS(?:CS|SE|IT| Information Technology| Computer Science| Software Engineering)?)",
            r"(HND [A-Za-z0-9()& ]{2,80})",
            r"(Master(?:s)?(?: in| of)? [A-Za-z ]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                value = normalize_whitespace(match.group(1))
                value = re.split(r"\b(University|College|Institute|School|FAST|NUCES|COMSATS|Bahria|UCP)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
                value = normalize_whitespace(value.strip(" -|,.;"))
                if value:
                    return value
        return ""

    def _extract_first_institution_phrase(self, cleaned: str) -> str:
        if not cleaned:
            return ""
        if "FAST NUCES" in cleaned.upper():
            return "FAST NUCES"

        split_cleaned = re.sub(r"(University|College|Institute|School)(?=[A-Z])", r"\1 | ", cleaned)
        split_cleaned = re.sub(r"(NUCES)(?=[A-Z])", r"\1 | ", split_cleaned)
        chunks = [normalize_whitespace(chunk) for chunk in split_cleaned.split("|") if normalize_whitespace(chunk)]
        for chunk in chunks:
            match = re.search(
                r"([A-Z][A-Za-z&().,\-]+(?: [A-Z][A-Za-z&().,\-]+){0,5}? "
                r"(?:University|College|Institute|School|NUCES|COMSATS|Bahria|UCP|NICON)"
                r"(?: University)?)",
                chunk,
            )
            if match:
                return normalize_whitespace(match.group(1))
        return ""

    def _should_use_openai_education_fallback(self, *, degree_title: str, institution: str, resume_text: str) -> bool:
        if not settings.OPENAI_API_KEY or not settings.RESUME_EDUCATION_OPENAI_FALLBACK:
            return False
        if self.provider != "openai":
            return False

        weak_degree = (
            not degree_title
            or len(degree_title) > 80
            or any(token in degree_title.lower() for token in ["project", "coursework", "optimized", "api communication"])
        )
        weak_institution = (
            not institution
            or len(institution) > 80
            or institution.lower() in {"college", "university", "institute", "school"}
        )
        has_education_signal = "education" in resume_text.lower() or "academic qualification" in resume_text.lower()
        return has_education_signal and (weak_degree or weak_institution)

    def _extract_structured_education_with_openai(self, resume_text: str) -> dict:
        system_prompt = (
            "Extract only the candidate's primary education information from the resume as strict JSON. "
            "Return keys: education_level, degree_title, education_institution, confidence. "
            "Choose the strongest or most relevant completed education entry. "
            "Do not include projects, coursework, dates, bullet points, job history, or cities in the institution name. "
            "If unclear, return empty strings."
        )
        result = self._call_openai_json(
            system_prompt=system_prompt,
            payload={"resume_text": resume_text[:16000]},
        )
        degree_title = truncate_text(str(result.get("degree_title", "")), 255)
        education_institution = truncate_text(str(result.get("education_institution", "")), 255)
        education_level = infer_education_level(
            f"{result.get('education_level', '')} {degree_title}"
        )
        return {
            "education_level": education_level,
            "degree_title": degree_title,
            "education_institution": education_institution,
            "confidence": float(result.get("confidence") or 0.0),
        }

    def _call_openai_json(self, *, system_prompt: str, payload: dict) -> dict:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.RESUME_PARSER_MODEL,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload)}]},
                ],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        body = response.json()
        text_chunks: list[str] = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    text_chunks.append(text)
        return json.loads("".join(text_chunks).strip())

    def _empty_result(self) -> dict:
        return {
            "skills": [],
            "education_level": "",
            "degree_title": "",
            "education_institution": "",
            "estimated_years_experience": 0.0,
            "experience_score": 0.0,
            "education_score": 0.0,
            "confidence": 0.0,
            "source": "empty",
        }

    @property
    def provider(self) -> str:
        return settings.RESUME_PARSER_PROVIDER.lower()
