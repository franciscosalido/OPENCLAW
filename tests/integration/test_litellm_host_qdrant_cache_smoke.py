from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.integration


def test_litellm_qdrant_cache_backend_is_reachable() -> None:
    if os.environ.get("RUN_LITELLM_QDRANT_CACHE_SMOKE") != "1":
        pytest.skip("RUN_LITELLM_QDRANT_CACHE_SMOKE=1 is required")

    qdrant_url = os.environ.get("QDRANT_API_BASE", "http://127.0.0.1:6333").rstrip("/")
    response = httpx.get(f"{qdrant_url}/healthz", timeout=3.0)

    assert response.status_code < 400
