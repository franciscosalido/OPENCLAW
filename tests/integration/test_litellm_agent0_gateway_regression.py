from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.integration


def test_agent0_gateway_regression_is_local_and_aliases_exist() -> None:
    if os.environ.get("QUIMERA_AGENT0_GATEWAY_REGRESSION") != "1":
        pytest.skip("QUIMERA_AGENT0_GATEWAY_REGRESSION=1 is required")

    base_url = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000").rstrip("/")
    api_key = os.environ.get("QUIMERA_LLM_API_KEY") or os.environ.get(
        "LITELLM_MASTER_KEY"
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    readiness = httpx.get(f"{base_url}/health/readiness", timeout=3.0)
    models = httpx.get(f"{base_url}/v1/models", headers=headers, timeout=5.0)

    assert readiness.status_code < 400
    assert models.status_code < 400
    names = {item["id"] for item in models.json().get("data", [])}
    assert {"local_chat", "local_rag", "quimera_embed"} <= names
