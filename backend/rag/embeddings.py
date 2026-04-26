"""Async Ollama embeddings client for local RAG."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.25
DEFAULT_MAX_CONCURRENCY = 4
TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

SleepFn = Callable[[float], Awaitable[None]]


@dataclass
class OllamaEmbedder:
    """Small async client for Ollama's local `/api/embed` endpoint."""

    model: str = DEFAULT_EMBED_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    client: httpx.AsyncClient | None = None
    sleep: SleepFn = asyncio.sleep
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")

        self.base_url = self.base_url.rstrip("/")
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
            )
            self._owns_client = True

    async def __aenter__(self) -> OllamaEmbedder:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP client, if this instance created it."""

        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def embed(self, text: str) -> list[float]:
        """Embed one text chunk using Ollama's local embedding API."""

        clean_text = _validate_text(text)
        response = await self._post_embed({"model": self.model, "input": clean_text})
        return _extract_single_embedding(response)

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple text chunks with bounded concurrency."""

        clean_texts = [_validate_text(text) for text in texts]
        if not clean_texts:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        return list(await asyncio.gather(*(embed_one(text) for text in clean_texts)))

    async def _post_embed(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.client is not None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post("/api/embed", json=payload)
                if response.status_code in TRANSIENT_STATUS_CODES:
                    response.raise_for_status()
                if response.status_code >= 400:
                    response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if not _should_retry(exc) or attempt >= self.max_retries:
                    raise
                await self.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError("unreachable retry state")


def _validate_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("text cannot be empty")
    return clean_text


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return False


def _extract_single_embedding(response: dict[str, Any]) -> list[float]:
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise ValueError("Ollama response did not include embeddings")

    first_embedding = embeddings[0]
    if not isinstance(first_embedding, list) or not first_embedding:
        raise ValueError("Ollama response included an invalid embedding")

    vector: list[float] = []
    for value in first_embedding:
        if not isinstance(value, int | float):
            raise ValueError("Ollama embedding contains a non-numeric value")
        vector.append(float(value))

    return vector

