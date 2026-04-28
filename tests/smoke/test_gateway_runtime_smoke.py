from __future__ import annotations

import json
import os
import time
from urllib.parse import urlparse

import httpx
import pytest
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    DEFAULT_LLM_REASONING_MODEL,
    ENV_LLM_API_KEY,
    GatewayChatClient,
    GatewayRuntimeConfig,
)

_SMOKE_OVERHEAD_SECONDS = 2.0
_MAX_SMOKE_REPEAT = 5


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_SMOKE") != "1",
    reason="LiteLLM runtime smoke skipped; set RUN_LITELLM_SMOKE=1 to enable.",
)


def _runtime_config() -> GatewayRuntimeConfig:
    if not os.environ.get(ENV_LLM_API_KEY):
        pytest.skip(f"{ENV_LLM_API_KEY} is required for LiteLLM runtime smoke.")
    return GatewayRuntimeConfig.from_env().validated()


def _smoke_repeat_count() -> int:
    raw = os.environ.get("RUN_LITELLM_SMOKE_REPEAT", "1")
    try:
        repeat = int(raw)
    except ValueError as exc:
        raise AssertionError(
            "RUN_LITELLM_SMOKE_REPEAT must be an integer between 1 and "
            f"{_MAX_SMOKE_REPEAT}."
        ) from exc
    if repeat < 1:
        raise AssertionError("RUN_LITELLM_SMOKE_REPEAT must be greater than zero.")
    return min(repeat, _MAX_SMOKE_REPEAT)


def _base_url_host(base_url: str) -> str:
    return urlparse(base_url).netloc or "unknown"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_litellm_runtime_aliases_respond() -> None:
    config = _runtime_config()
    repeat_count = _smoke_repeat_count()
    base_url_host = _base_url_host(config.base_url)
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
            timeout_budget = config.resolve_timeout(alias)
            allowed_elapsed = timeout_budget + _SMOKE_OVERHEAD_SECONDS
            latencies: list[float] = []
            for attempt in range(1, repeat_count + 1):
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
                        f"LiteLLM alias {alias!r} failed at {base_url_host}. "
                        "Check LiteLLM, Ollama, QUIMERA_LLM_API_KEY, and "
                        "configured aliases."
                    ) from exc

                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                assert answer.strip(), (
                    f"LiteLLM alias {alias!r} returned an empty answer at "
                    f"{base_url_host}."
                )
                assert elapsed < allowed_elapsed, (
                    f"LiteLLM alias {alias!r} exceeded timeout budget at "
                    f"{base_url_host}: elapsed={elapsed:.2f}s "
                    f"timeout_budget={timeout_budget:.1f}s "
                    f"allowed={allowed_elapsed:.1f}s attempt={attempt}/"
                    f"{repeat_count}."
                )
                if alias == os.environ.get(
                    "QUIMERA_LLM_JSON_MODEL",
                    DEFAULT_LLM_JSON_MODEL,
                ):
                    try:
                        json.loads(answer)
                    except json.JSONDecodeError as exc:
                        raise AssertionError(
                            f"LiteLLM JSON alias {alias!r} did not return "
                            f"parseable JSON at {base_url_host}."
                        ) from exc
            compact_latencies = ", ".join(f"{latency:.2f}s" for latency in latencies)
            logger.info(
                f"smoke alias={alias} host={base_url_host} repeat={repeat_count} "
                f"timeout_s={timeout_budget:.1f} latencies=[{compact_latencies}]"
            )


@pytest.mark.smoke
def test_litellm_models_endpoint_exposes_runtime_aliases() -> None:
    config = _runtime_config()
    models_url = f"{config.base_url.rstrip('/')}/models"
    base_url_host = _base_url_host(config.base_url)
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
        raise AssertionError(
            f"LiteLLM /models returned HTTP {exc.response.status_code} at "
            f"{base_url_host}."
        ) from exc
    except httpx.RequestError as exc:
        raise AssertionError(
            f"LiteLLM /models is not reachable at {base_url_host}. Start "
            "infra/litellm/start_litellm.sh."
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
