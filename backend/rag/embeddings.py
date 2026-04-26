"""Async Ollama embeddings client for OPENCLAW RAG pipeline.

Calls Ollama /api/embed endpoint directly.
No sentence-transformers dependency.
All configuration is injected at construction time.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from loguru import logger


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0  # backoff: 1s -> 2s -> 4s
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_EXPECTED_DIMENSIONS = 768

TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

SleepFn = Callable[[float], Awaitable[None]]


class EmbeddingError(Exception):
    """Raised when embedding fails after all retries or response is invalid.

    Covers: wrong dimensions, empty embeddings, non-numeric values.
    """


@dataclass
class OllamaEmbedder:
    """Async embedding client backed by Ollama /api/embed.

    Usage (preferred — auto-closes client)::

        async with OllamaEmbedder() as embedder:
            vector = await embedder.embed("texto aqui")
            vectors = await embedder.embed_batch(["a", "b", "c"])

    All parameters match rag_config.yaml embedding section.
    Never use sentence-transformers — Ollama handles inference.
    """

    model: str = DEFAULT_EMBED_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    expected_dimensions: int = DEFAULT_EXPECTED_DIMENSIONS
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
        if self.expected_dimensions <= 0:
            raise ValueError("expected_dimensions must be greater than zero")

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
        """Embed one text string via Ollama /api/embed.

        Args:
            text: Non-empty string to embed.

        Returns:
            Dense float vector with exactly expected_dimensions elements.

        Raises:
            ValueError: If text is empty or whitespace.
            EmbeddingError: If Ollama returns wrong dimensions or invalid response.
            httpx.HTTPStatusError: On non-transient HTTP errors after all retries.
        """
        clean_text = _validate_text(text)
        t0 = time.monotonic()

        response = await self._post_embed({"model": self.model, "input": clean_text})
        vector = _extract_single_embedding(response)

        if len(vector) != self.expected_dimensions:
            raise EmbeddingError(
                f"Expected {self.expected_dimensions} dimensions, "
                f"got {len(vector)} from model '{self.model}'"
            )

        latency_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "embed | model={} dims={} latency={:.1f}ms",
            self.model,
            len(vector),
            latency_ms,
        )
        return vector

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple texts with bounded concurrency.

        Args:
            texts: Sequence of non-empty strings.

        Returns:
            List of vectors in the same order as input texts.

        Raises:
            ValueError: If any text is empty or whitespace.
            EmbeddingError: If any response has wrong dimensions or invalid format.
        """
        clean_texts = [_validate_text(t) for t in texts]
        if not clean_texts:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)
        t0 = time.monotonic()

        async def _embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        vectors = list(
            await asyncio.gather(*(_embed_one(t) for t in clean_texts))
        )

        latency_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "embed_batch | model={} count={} latency={:.1f}ms",
            self.model,
            len(vectors),
            latency_ms,
        )
        return vectors

    async def _post_embed(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("HTTP client is not initialized")

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post("/api/embed", json=payload)
                if response.status_code >= 400:
                    response.raise_for_status()
                return cast(dict[str, Any], response.json())
            except (
                httpx.TimeoutException,
                httpx.TransportError,
                httpx.HTTPStatusError,
            ) as exc:
                if not _should_retry(exc) or attempt >= self.max_retries:
                    raise
                wait = self.backoff_seconds * (2**attempt)
                logger.debug(
                    "embed retry | attempt={} wait={:.2f}s", attempt + 1, wait
                )
                await self.sleep(wait)

        raise RuntimeError("unreachable retry state")  # pragma: no cover


def _validate_text(text: str) -> str:
    """Strip and validate that text is a non-empty string."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    clean = text.strip()
    if not clean:
        raise ValueError("text cannot be empty or whitespace")
    return clean


def _should_retry(exc: Exception) -> bool:
    """Return True for transient network and server errors."""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return False


def _extract_single_embedding(response: dict[str, Any]) -> list[float]:
    """Extract and coerce the first embedding from an Ollama /api/embed response."""
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise EmbeddingError("Ollama response did not include embeddings")

    first = embeddings[0]
    if not isinstance(first, list) or not first:
        raise EmbeddingError("Ollama response included an empty embedding vector")

    vector: list[float] = []
    for value in first:
        if not isinstance(value, (int, float)):
            raise EmbeddingError("Ollama embedding contains a non-numeric value")
        vector.append(float(value))

    return vector
