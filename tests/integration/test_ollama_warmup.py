from __future__ import annotations

import os

import httpx
import pytest

from infra.ollama.config import load_ollama_config
from infra.ollama.shutdown_hook import release_all_models
from infra.ollama.warmup import warmup_all_models


pytestmark = pytest.mark.integration


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


async def _skip_if_ollama_unavailable(base_url: str) -> None:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=3.0) as client:
            response = await client.get("/api/version")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"Ollama unavailable at {base_url}: {exc.__class__.__name__}")


async def _skip_if_models_missing(base_url: str, models: set[str]) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=3.0) as client:
        response = await client.get("/api/tags")
        response.raise_for_status()
    names = {item["name"] for item in response.json().get("models", [])}
    missing = sorted(model for model in models if model not in names)
    if missing:
        pytest.skip(f"rode: ollama pull {missing[0]}")


@pytest.mark.asyncio
async def test_ollama_version_and_warmup_release_roundtrip() -> None:
    base_url = _ollama_base_url()
    await _skip_if_ollama_unavailable(base_url)
    config = load_ollama_config()
    await _skip_if_models_missing(base_url, {config.embed_model, config.chat_model})

    warmup_result = await warmup_all_models(config)
    release_result = await release_all_models(config)

    assert set(warmup_result) == {config.embed_model, config.chat_model}
    assert set(release_result) == {config.embed_model, config.chat_model}
