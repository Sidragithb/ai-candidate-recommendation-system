import re
from collections import Counter


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def split_skills(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,/\n|]+", value or "")

    seen: set[str] = set()
    skills: list[str] = []
    for item in raw_items:
        cleaned = normalize_whitespace(str(item)).strip(" -")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        skills.append(cleaned)
    return skills


def tokenize_keywords(value: str) -> list[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "or",
        "the",
        "for",
        "with",
        "to",
        "of",
        "in",
        "on",
        "or",
        "is",
        "are",
        "as",
        "at",
        "by",
        "from",
        "will",
        "be",
        "you",
        "your",
        "candidate",
        "candidates",
        "best",
        "show",
        "experience",
        "year",
        "years",
        "developer",
        "developers",
    }
    tokens = re.findall(r"[A-Za-z0-9.+#-]{2,}", (value or "").lower())
    return [token for token in tokens if token not in stop_words and not token.isdigit()]


def keyword_frequency(value: str) -> Counter[str]:
    return Counter(tokenize_keywords(value))


def extract_years_experience(resume_text: str) -> float:
    text = (resume_text or "").lower()
    numeric_matches = re.findall(r"(\d+(?:\.\d+)?)\+?\s+years?", text)
    if numeric_matches:
        return max(float(value) for value in numeric_matches)

    years = [int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if len(years) >= 2:
        return float(max(max(years) - min(years), 0))
    return 0.0


def infer_education_level(value: str) -> str:
    normalized = (value or "").lower()
    if any(token in normalized for token in ["phd", "ph.d", "doctor of philosophy"]):
        return "PhD"
    if any(token in normalized for token in ["master", "msc", "m.s", "mba", "ms "]):
        return "Masters"
    if any(token in normalized for token in ["bachelor", "bsc", "b.s", "bs ", "bscs", "bsse", "bsit", "be ", "hnd"]):
        return "Bachelors"
    if any(token in normalized for token in ["intermediate", "college", "fsc", "a-level"]):
        return "Intermediate"
    return ""


def education_score(level: str) -> float:
    return {
        "PhD": 1.0,
        "Masters": 0.85,
        "Bachelors": 0.7,
        "Intermediate": 0.4,
        "": 0.0,
    }.get(level or "", 0.0)


def experience_score(years_experience: float) -> float:
    return min(round(max(years_experience, 0.0) / 8.0, 4), 1.0)


def truncate_text(value: str, max_length: int) -> str:
    cleaned = normalize_whitespace(value)
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."
