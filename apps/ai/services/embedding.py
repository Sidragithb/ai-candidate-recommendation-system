import httpx
from django.conf import settings


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        normalized = text.strip()
        if not normalized:
            return [0.0] * settings.EMBEDDING_VECTOR_SIZE

        if self.provider == "openai":
            return self._embed_with_openai(normalized)
        if self.provider == "ollama":
            return self._embed_with_ollama(normalized)
        return self._embed_with_placeholder(normalized)

    def _embed_with_placeholder(self, text: str) -> list[float]:
        normalized = text.lower()
        length_score = min(len(normalized) / 100.0, 1.0)
        token_score = min(len(normalized.split()) / 20.0, 1.0)
        checksum_score = (sum(ord(char) for char in normalized) % 1000) / 1000.0
        vector = [length_score, token_score, checksum_score]
        target_size = settings.EMBEDDING_VECTOR_SIZE
        if len(vector) >= target_size:
            return vector[:target_size]
        return vector + ([0.0] * (target_size - len(vector)))

    def _embed_with_openai(self, text: str) -> list[float]:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.EMBEDDING_MODEL,
                "input": text,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["data"][0]["embedding"]

    def _embed_with_ollama(self, text: str) -> list[float]:
        attempts = [text]
        if len(text) > 12000:
            attempts.append(text[:12000])
        if len(text) > 6000:
            attempts.append(text[:6000])
        if len(text) > 3000:
            attempts.append(text[:3000])

        last_error = None
        seen_lengths = set()
        for attempt_text in attempts:
            if len(attempt_text) in seen_lengths:
                continue
            seen_lengths.add(len(attempt_text))
            try:
                response = httpx.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={
                        "model": settings.EMBEDDING_MODEL,
                        "prompt": attempt_text,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()
                return payload["embedding"]
            except httpx.HTTPError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to generate Ollama embedding.")

    @property
    def provider(self) -> str:
        return settings.EMBEDDING_PROVIDER.lower()

    @property
    def model(self) -> str:
        return settings.EMBEDDING_MODEL
