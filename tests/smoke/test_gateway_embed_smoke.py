from __future__ import annotations

import math
import os
import time
from urllib.parse import urlparse

import httpx
import pytest
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_EMBED_MODEL,
    ENV_LLM_API_KEY,
    GatewayRuntimeConfig,
)
from backend.gateway.embed_client import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    GatewayEmbedClient,
)


_SYNTHETIC_TEXT = "Documento sintetico sobre diversificacao educacional."
_SYNTHETIC_BATCH = [
    "Cenario sintetico de renda fixa.",
    "Cenario sintetico de fundos imobiliarios.",
]

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_EMBED_SMOKE") != "1",
    reason=(
        "LiteLLM embedding smoke skipped; set RUN_LITELLM_EMBED_SMOKE=1 "
        "to enable."
    ),
)


def _runtime_config() -> GatewayRuntimeConfig:
    if not os.environ.get(ENV_LLM_API_KEY):
        pytest.skip(f"{ENV_LLM_API_KEY} is required for LiteLLM embedding smoke.")
    return GatewayRuntimeConfig.from_env().validated()


def _base_url_host(base_url: str) -> str:
    return urlparse(base_url).netloc or "unknown"


def _assert_vector(vector: list[float], *, label: str) -> None:
    assert len(vector) == DEFAULT_EMBEDDING_DIMENSIONS, (
        f"{label} returned {len(vector)} dimensions; expected "
        f"{DEFAULT_EMBEDDING_DIMENSIONS}."
    )
    assert all(isinstance(value, float) for value in vector), (
        f"{label} returned a non-float value."
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


async def _direct_ollama_embed(text: str) -> list[float]:
    base_url = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        response = await client.post("/api/embed", json={"model": model, "input": text})
        response.raise_for_status()
    body = response.json()
    embeddings = body.get("embeddings")
    assert isinstance(embeddings, list) and embeddings, (
        "Direct Ollama response did not include embeddings."
    )
    first = embeddings[0]
    assert isinstance(first, list), "Direct Ollama embedding is not a list."
    return [float(value) for value in first]


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_litellm_local_embed_single_and_batch() -> None:
    config = _runtime_config()
    host = _base_url_host(config.base_url)
    async with GatewayEmbedClient(config=config) as embedder:
        single_start = time.perf_counter()
        single = await embedder.embed(_SYNTHETIC_TEXT)
        single_latency = time.perf_counter() - single_start

        batch_start = time.perf_counter()
        batch = await embedder.embed_batch(_SYNTHETIC_BATCH)
        batch_latency = time.perf_counter() - batch_start

    _assert_vector(single, label=DEFAULT_LLM_EMBED_MODEL)
    assert len(batch) == len(_SYNTHETIC_BATCH)
    for vector in batch:
        _assert_vector(vector, label=f"{DEFAULT_LLM_EMBED_MODEL} batch")

    logger.info(
        "embed_smoke alias={} host={} single_latency_s={:.2f} "
        "batch_latency_s={:.2f} dims={} batch_count={}",
        DEFAULT_LLM_EMBED_MODEL,
        host,
        single_latency,
        batch_latency,
        len(single),
        len(batch),
    )


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_litellm_local_embed_matches_direct_ollama_dimension() -> None:
    config = _runtime_config()
    host = _base_url_host(config.base_url)

    async with GatewayEmbedClient(config=config) as embedder:
        gateway_start = time.perf_counter()
        gateway_vector = await embedder.embed(_SYNTHETIC_TEXT)
        gateway_latency = time.perf_counter() - gateway_start

    direct_start = time.perf_counter()
    direct_vector = await _direct_ollama_embed(_SYNTHETIC_TEXT)
    direct_latency = time.perf_counter() - direct_start

    _assert_vector(gateway_vector, label=DEFAULT_LLM_EMBED_MODEL)
    _assert_vector(direct_vector, label="direct Ollama")

    cosine = _cosine_similarity(gateway_vector, direct_vector)
    logger.info(
        "embed_parity alias={} host={} gateway_latency_s={:.2f} "
        "direct_latency_s={:.2f} cosine_similarity={:.6f}",
        DEFAULT_LLM_EMBED_MODEL,
        host,
        gateway_latency,
        direct_latency,
        cosine,
    )
