from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from backend.gateway.client import (
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    DEFAULT_LLM_REASONING_MODEL,
    ENV_LLM_API_KEY,
    GatewayChatClient,
    GatewayRuntimeConfig,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_SMOKE") != "1",
    reason="LiteLLM runtime smoke skipped; set RUN_LITELLM_SMOKE=1 to enable.",
)


def _runtime_config() -> GatewayRuntimeConfig:
    if not os.environ.get(ENV_LLM_API_KEY):
        pytest.skip(f"{ENV_LLM_API_KEY} is required for LiteLLM runtime smoke.")
    return GatewayRuntimeConfig.from_env().validated()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_litellm_runtime_aliases_respond() -> None:
    config = _runtime_config()
    cases = [
        (
            os.environ.get("QUIMERA_LLM_MODEL", DEFAULT_LLM_MODEL),
            "Explique em uma frase o que e risco de concentracao.",
            None,
        ),
        (
            os.environ.get("QUIMERA_LLM_REASONING_MODEL", DEFAULT_LLM_REASONING_MODEL),
            "Planeje em uma frase como revisar uma hipotese sintetica.",
            None,
        ),
        (
            os.environ.get("QUIMERA_LLM_RAG_MODEL", DEFAULT_LLM_RAG_MODEL),
            "Classifique esta pergunta sintetica: carteira hipotetica com 50% em FIIs.",
            None,
        ),
        (
            os.environ.get("QUIMERA_LLM_JSON_MODEL", DEFAULT_LLM_JSON_MODEL),
            (
                "Responda somente JSON valido, sem markdown: "
                '{"classe":"alocacao_sintetica","fiis":50,"renda_fixa":30,"acoes":20}'
            ),
            {"type": "json_object"},
        ),
    ]

    async with GatewayChatClient(config=config) as client:
        for alias, prompt, response_format in cases:
            start = time.perf_counter()
            try:
                answer = await client.chat_completion(
                    [{"role": "user", "content": prompt}],
                    model=alias,
                    temperature=0.0,
                    max_tokens=96,
                    response_format=response_format,
                )
            except Exception as exc:
                raise AssertionError(
                    f"LiteLLM alias {alias!r} failed. Check LiteLLM, Ollama, "
                    "QUIMERA_LLM_API_KEY, and configured aliases."
                ) from exc

            assert answer.strip(), f"LiteLLM alias {alias!r} returned an empty answer"
            assert (time.perf_counter() - start) < 120, (
                f"LiteLLM alias {alias!r} exceeded the smoke timeout"
            )
            if alias == os.environ.get("QUIMERA_LLM_JSON_MODEL", DEFAULT_LLM_JSON_MODEL):
                try:
                    json.loads(answer)
                except json.JSONDecodeError as exc:
                    raise AssertionError(
                        f"LiteLLM JSON alias {alias!r} did not return parseable JSON: "
                        f"{answer[:120]!r}"
                    ) from exc


@pytest.mark.smoke
def test_litellm_models_endpoint_exposes_runtime_aliases() -> None:
    config = _runtime_config()
    models_url = f"{config.base_url.rstrip('/')}/models"
    try:
        response = httpx.get(
            models_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise AssertionError(
                "LiteLLM authentication failed. QUIMERA_LLM_API_KEY should match "
                "LITELLM_MASTER_KEY."
            ) from exc
        raise AssertionError(f"LiteLLM /models returned HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise AssertionError(
            f"LiteLLM /models is not reachable at {models_url}. "
            "Start infra/litellm/start_litellm.sh."
        ) from exc

    body = response.json()
    data = body.get("data")
    assert isinstance(data, list), "LiteLLM /models response is missing a data list"
    seen = {
        str(item.get("id") or item.get("model_name") or item.get("model") or "")
        for item in data
        if isinstance(item, dict)
    }
    expected = {
        os.environ.get("QUIMERA_LLM_MODEL", DEFAULT_LLM_MODEL),
        os.environ.get("QUIMERA_LLM_REASONING_MODEL", DEFAULT_LLM_REASONING_MODEL),
        os.environ.get("QUIMERA_LLM_RAG_MODEL", DEFAULT_LLM_RAG_MODEL),
        os.environ.get("QUIMERA_LLM_JSON_MODEL", DEFAULT_LLM_JSON_MODEL),
    }
    missing = sorted(expected - seen)
    assert not missing, f"LiteLLM /models is missing aliases: {missing}"
