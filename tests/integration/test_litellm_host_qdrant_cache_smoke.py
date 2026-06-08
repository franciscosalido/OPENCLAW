from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import yaml

from infra.litellm.render_config import render_runtime_config


pytestmark = pytest.mark.integration


def test_litellm_qdrant_cache_backend_is_reachable() -> None:
    if os.environ.get("RUN_LITELLM_QDRANT_CACHE_SMOKE") != "1":
        pytest.skip("RUN_LITELLM_QDRANT_CACHE_SMOKE=1 is required")

    qdrant_url = os.environ.get("QDRANT_API_BASE", "http://127.0.0.1:6333").rstrip("/")
    response = httpx.get(f"{qdrant_url}/readyz", timeout=3.0)
    if response.status_code >= 400:
        response = httpx.get(f"{qdrant_url}/healthz", timeout=3.0)

    assert response.status_code < 400

    collections = httpx.get(f"{qdrant_url}/collections", timeout=3.0)
    assert collections.status_code < 400


def test_litellm_qdrant_semantic_cache_runtime_policy(tmp_path: Path) -> None:
    if os.environ.get("RUN_LITELLM_QDRANT_CACHE_SMOKE") != "1":
        pytest.skip("RUN_LITELLM_QDRANT_CACHE_SMOKE=1 is required")

    runtime = tmp_path / "runtime.yaml"
    result = render_runtime_config(
        source_path=Path("infra/litellm/litellm_config.yaml"),
        runtime_path=runtime,
        env={
            "LITELLM_MASTER_KEY": os.environ.get("LITELLM_MASTER_KEY", "local-dev-key"),
            "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL": os.environ.get(
                "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL",
                "0",
            ),
            "QDRANT_API_BASE": os.environ.get(
                "QDRANT_API_BASE", "http://127.0.0.1:6333"
            ),
        },
    )
    rendered = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    cache_type = rendered["litellm_settings"]["cache_params"]["type"]

    if os.environ.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") == "1":
        assert result.cache_backend in {"qdrant-semantic", "local", "in-memory"}
    else:
        assert cache_type in {"local", "in-memory"}
