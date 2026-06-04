from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.integration


def test_litellm_host_gateway_readiness_and_models() -> None:
    if os.environ.get("RUN_LITELLM_HOST_SMOKE") != "1":
        pytest.skip("RUN_LITELLM_HOST_SMOKE=1 is required")

    base_url = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")
    headers = {}
    if key := os.environ.get("QUIMERA_LLM_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"

    readiness = httpx.get(f"{base_url}/health/readiness", timeout=3.0)
    liveliness = httpx.get(f"{base_url}/health/liveliness", timeout=3.0)
    models = httpx.get(f"{base_url}/v1/models", headers=headers, timeout=5.0)

    assert readiness.status_code < 400
    assert liveliness.status_code < 400
    assert models.status_code < 400

    if os.environ.get("QUIMERA_LITELLM_TEST_HEALTH") == "1":
        health = httpx.get(f"{base_url}/health", headers=headers, timeout=60.0)
        assert health.status_code < 400

    if os.environ.get("QUIMERA_LITELLM_TEST_CHAT") == "1":
        chat = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "model": "local_chat",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
            timeout=130.0,
        )
        assert chat.status_code < 400

    if os.environ.get("QUIMERA_LITELLM_TEST_EMBED") == "1":
        embed = httpx.post(
            f"{base_url}/v1/embeddings",
            headers={**headers, "Content-Type": "application/json"},
            json={"model": "quimera_embed", "input": "ping"},
            timeout=20.0,
        )
        assert embed.status_code < 400
