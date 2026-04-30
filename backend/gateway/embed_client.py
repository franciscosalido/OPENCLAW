"""OpenAI-compatible embeddings client for the local LiteLLM gateway."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_EMBED_MODEL,
    GatewayRuntimeConfig,
)
from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConfigurationError,
    GatewayConnectionError,
    GatewayResponseError,
    GatewayTimeoutError,
)


ENV_LLM_EMBED_MODEL = "QUIMERA_LLM_EMBED_MODEL"
DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_EMBED_MAX_RETRIES = 3
DEFAULT_EMBED_BACKOFF_SECONDS = 1.0
DEFAULT_EMBED_MAX_CONCURRENCY = 4
TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

SleepFn = Callable[[float], Awaitable[None]]


@dataclass
class GatewayEmbedClient:
    """Small async client for LiteLLM ``/embeddings`` calls."""

    config: GatewayRuntimeConfig = field(
        default_factory=lambda: GatewayRuntimeConfig.from_env().validated()
    )
    model: str = field(
        default_factory=lambda: os.environ.get(
            ENV_LLM_EMBED_MODEL,
            DEFAULT_LLM_EMBED_MODEL,
        )
    )
    expected_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    max_retries: int = DEFAULT_EMBED_MAX_RETRIES
    backoff_seconds: float = DEFAULT_EMBED_BACKOFF_SECONDS
    max_concurrency: int = DEFAULT_EMBED_MAX_CONCURRENCY
    client: httpx.AsyncClient | None = None
    sleep: SleepFn = asyncio.sleep
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.config = self.config.validated()
        self.model = self.model.strip()
        if not self.model:
            raise GatewayConfigurationError(f"{ENV_LLM_EMBED_MODEL} cannot be empty")
        if self.expected_dimensions <= 0:
            raise GatewayConfigurationError(
                "expected_dimensions must be greater than zero"
            )
        if self.max_retries < 0:
            raise GatewayConfigurationError("max_retries cannot be negative")
        if self.backoff_seconds < 0:
            raise GatewayConfigurationError("backoff_seconds cannot be negative")
        if self.max_concurrency <= 0:
            raise GatewayConfigurationError("max_concurrency must be greater than zero")
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
            self._owns_client = True

    async def __aenter__(self) -> GatewayEmbedClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def embed(self, text: str) -> list[float]:
        """Embed one synthetic/local text through LiteLLM ``/embeddings``."""
        clean_text = _validate_text(text)
        vectors = await self._embed_payload(clean_text)
        if len(vectors) != 1:
            raise GatewayResponseError(
                "LiteLLM embedding response did not contain exactly one vector.",
                alias=self.model,
            )
        return vectors[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a small batch through LiteLLM ``/embeddings``."""
        clean_texts = [_validate_text(text) for text in texts]
        if not clean_texts:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _embed_one(text: str) -> list[float]:
            async with semaphore:
                vectors = await self._embed_payload(text)
                if len(vectors) != 1:
                    raise GatewayResponseError(
                        "LiteLLM embedding response did not contain exactly one vector.",
                        alias=self.model,
                    )
                return vectors[0]

        return list(await asyncio.gather(*(_embed_one(text) for text in clean_texts)))

    async def _embed_payload(self, input_value: str | list[str]) -> list[list[float]]:
        if self.client is None:
            raise GatewayConnectionError("Gateway HTTP client is not initialized")

        request_timeout = self.config.resolve_timeout(self.model)
        payload: dict[str, object] = {"model": self.model, "input": input_value}
        start = time.perf_counter()

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    "/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=request_timeout,
                )
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                _log_embed_call(
                    model_alias=self.model,
                    started_at=start,
                    timeout_s=request_timeout,
                    status="failure",
                    error_category="timeout",
                )
                raise GatewayTimeoutError(
                    "Timed out calling local LiteLLM embeddings gateway.",
                    alias=self.model,
                ) from exc
            except httpx.RequestError as exc:
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                _log_embed_call(
                    model_alias=self.model,
                    started_at=start,
                    timeout_s=request_timeout,
                    status="failure",
                    error_category="connection",
                )
                raise GatewayConnectionError(
                    "Could not reach local LiteLLM embeddings gateway. "
                    "Start infra/litellm/start_litellm.sh and verify /v1/models.",
                    alias=self.model,
                ) from exc

            if response.status_code in {401, 403}:
                _log_embed_call(
                    model_alias=self.model,
                    started_at=start,
                    timeout_s=request_timeout,
                    status="failure",
                    error_category="authentication",
                )
                raise GatewayAuthenticationError(
                    "LiteLLM embeddings gateway authentication failed. "
                    "QUIMERA_LLM_API_KEY should match LITELLM_MASTER_KEY.",
                    alias=self.model,
                )
            if response.status_code >= 400:
                if (
                    response.status_code in TRANSIENT_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    await self._sleep_before_retry(attempt)
                    continue
                _log_embed_call(
                    model_alias=self.model,
                    started_at=start,
                    timeout_s=request_timeout,
                    status="failure",
                    error_category=f"http_{response.status_code}",
                )
                raise GatewayResponseError(
                    f"LiteLLM embeddings gateway returned HTTP {response.status_code}.",
                    alias=self.model,
                )

            try:
                body = cast(dict[str, Any], response.json())
            except ValueError as exc:
                raise GatewayResponseError(
                    "LiteLLM embeddings gateway returned invalid JSON.",
                    alias=self.model,
                ) from exc

            vectors = _extract_embeddings(
                body,
                expected_dimensions=self.expected_dimensions,
                alias=self.model,
            )
            _log_embed_call(
                model_alias=self.model,
                started_at=start,
                timeout_s=request_timeout,
                status="success",
                error_category=None,
            )
            return vectors

        raise RuntimeError("unreachable retry state")  # pragma: no cover

    async def _sleep_before_retry(self, attempt: int) -> None:
        wait_seconds = self.backoff_seconds * (2**attempt)
        logger.debug(
            "gateway_embed_retry | model_alias={} attempt={} wait_s={:.2f}",
            self.model,
            attempt + 1,
            wait_seconds,
        )
        await self.sleep(wait_seconds)


def _validate_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    clean = text.strip()
    if not clean:
        raise ValueError("text cannot be empty or whitespace")
    return clean


def _extract_embeddings(
    body: dict[str, Any],
    *,
    expected_dimensions: int,
    alias: str,
) -> list[list[float]]:
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise GatewayResponseError(
            "LiteLLM embeddings response did not include data.",
            alias=alias,
        )

    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            raise GatewayResponseError(
                "LiteLLM embeddings response item is invalid.",
                alias=alias,
            )
        vector = _coerce_embedding_vector(
            item.get("embedding"),
            expected_dimensions=expected_dimensions,
            alias=alias,
        )
        vectors.append(vector)
    return vectors


def _coerce_embedding_vector(
    raw_vector: object,
    *,
    expected_dimensions: int,
    alias: str,
) -> list[float]:
    if not isinstance(raw_vector, list) or not raw_vector:
        raise GatewayResponseError(
            "LiteLLM embeddings response item did not include a vector.",
            alias=alias,
        )
    if len(raw_vector) != expected_dimensions:
        raise GatewayResponseError(
            f"Expected {expected_dimensions} embedding dimensions, "
            f"got {len(raw_vector)}.",
            alias=alias,
        )

    vector: list[float] = []
    for value in raw_vector:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise GatewayResponseError(
                "LiteLLM embedding vector contains a non-numeric value.",
                alias=alias,
            )
        vector.append(float(value))
    return vector


def _log_embed_call(
    *,
    model_alias: str,
    started_at: float,
    timeout_s: float,
    status: str,
    error_category: str | None,
) -> None:
    logger.debug(
        "gateway_embed | model_alias={} latency_ms={:.1f} timeout_s={:.1f} "
        "status={} error_category={}",
        model_alias,
        (time.perf_counter() - started_at) * 1000,
        timeout_s,
        status,
        error_category or "none",
    )
