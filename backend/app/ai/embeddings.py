from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings
from app.services.observability import trace_span

settings = get_settings()


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingResponse:
    provider: str
    model: str
    vectors: list[list[float]]
    duration_ms: int
    attempts: int


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    async def embed_many(self, texts: list[str]) -> EmbeddingResponse:
        ...


def _normalize_vector(raw_vector: object) -> list[float]:
    if not isinstance(raw_vector, list) or not raw_vector:
        raise EmbeddingProviderError("Embedding provider returned an empty vector.")
    vector: list[float] = []
    for value in raw_vector:
        if not isinstance(value, (int, float)):
            raise EmbeddingProviderError("Embedding provider returned a non-numeric vector value.")
        vector.append(float(value))
    return vector


class BaseHTTPEmbeddingProvider:
    provider_name = "http_embedding"

    def __init__(
        self,
        *,
        model_name: str,
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)

    async def embed_many(self, texts: list[str]) -> EmbeddingResponse:
        if not texts:
            return EmbeddingResponse(
                provider=self.provider_name,
                model=self.model_name,
                vectors=[],
                duration_ms=0,
                attempts=0,
            )
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with trace_span(
                    "tolmach.embedding_call",
                    {
                        "provider": self.provider_name,
                        "model": self.model_name,
                        "attempt": attempt,
                        "batch_size": len(texts),
                    },
                ):
                    vectors = await self._request_vectors(texts)
                if len(vectors) != len(texts):
                    raise EmbeddingProviderError(
                        f"Embedding provider returned {len(vectors)} vectors for {len(texts)} texts."
                    )
                return EmbeddingResponse(
                    provider=self.provider_name,
                    model=self.model_name,
                    vectors=vectors,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempt,
                )
            except (httpx.HTTPError, EmbeddingProviderError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(min(1.0, 0.2 * attempt))
        raise EmbeddingProviderError(
            f"{self.provider_name} embeddings request failed after retries: {last_error}"
        ) from last_error

    async def _request_vectors(self, texts: list[str]) -> list[list[float]]:
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._endpoint_url(),
                json=self._request_body(texts),
                headers=self._request_headers(),
            )
            response.raise_for_status()
        return self._extract_vectors(response.json())

    def _endpoint_url(self) -> str:
        raise NotImplementedError

    def _request_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _request_body(self, texts: list[str]) -> dict:
        raise NotImplementedError

    def _extract_vectors(self, payload: dict) -> list[list[float]]:
        raise NotImplementedError


class ProductionEmbeddingProvider(BaseHTTPEmbeddingProvider):
    provider_name = "production"

    def __init__(self) -> None:
        if not settings.production_llm_base_url:
            raise EmbeddingProviderError("PRODUCTION_LLM_BASE_URL must be set for production embeddings.")
        if not settings.production_llm_api_key:
            raise EmbeddingProviderError("PRODUCTION_LLM_API_KEY must be set for production embeddings.")
        model_name = settings.embedding_model or settings.production_llm_model or settings.llm_model
        if not model_name:
            raise EmbeddingProviderError("EMBEDDING_MODEL must be set for production embeddings.")
        super().__init__(
            model_name=model_name,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )

    def _endpoint_url(self) -> str:
        return f"{settings.production_llm_base_url.rstrip('/')}/embeddings"

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.production_llm_api_key}",
            "Content-Type": "application/json",
        }

    def _request_body(self, texts: list[str]) -> dict:
        return {
            "model": self.model_name,
            "input": texts,
        }

    def _extract_vectors(self, payload: dict) -> list[list[float]]:
        raw_items = payload.get("data")
        if not isinstance(raw_items, list):
            raise EmbeddingProviderError("Production embeddings payload does not contain a data array.")
        ordered_items = sorted(raw_items, key=lambda item: int(item.get("index", 0)))
        return [_normalize_vector(item.get("embedding")) for item in ordered_items]


class OllamaEmbeddingProvider(BaseHTTPEmbeddingProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        model_name = settings.embedding_model or settings.llm_model
        if not model_name:
            raise EmbeddingProviderError("EMBEDDING_MODEL or LLM_MODEL must be set for Ollama embeddings.")
        super().__init__(
            model_name=model_name,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )

    def _endpoint_url(self) -> str:
        return f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"

    def _request_body(self, texts: list[str]) -> dict:
        if len(texts) != 1:
            raise EmbeddingProviderError("Ollama embedding endpoint is used one text at a time.")
        return {
            "model": self.model_name,
            "prompt": texts[0],
        }

    async def embed_many(self, texts: list[str]) -> EmbeddingResponse:
        started = time.perf_counter()
        vectors: list[list[float]] = []
        attempts = 0
        for text in texts:
            response = await super().embed_many([text])
            vectors.extend(response.vectors)
            attempts += response.attempts
        return EmbeddingResponse(
            provider=self.provider_name,
            model=self.model_name,
            vectors=vectors,
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
        )

    def _extract_vectors(self, payload: dict) -> list[list[float]]:
        vector = payload.get("embedding")
        if vector is None:
            raise EmbeddingProviderError("Ollama embeddings payload does not contain embedding.")
        return [_normalize_vector(vector)]


def create_embedding_provider() -> EmbeddingProvider | None:
    provider_name = settings.embedding_provider.strip().lower()
    if provider_name in {"", "disabled", "none"}:
        return None
    if provider_name == "production":
        return ProductionEmbeddingProvider()
    if provider_name == "ollama":
        return OllamaEmbeddingProvider()
    raise EmbeddingProviderError(f"Unsupported EMBEDDING_PROVIDER value: {settings.embedding_provider}")
