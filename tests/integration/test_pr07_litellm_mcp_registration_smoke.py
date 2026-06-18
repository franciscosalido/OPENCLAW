from __future__ import annotations

import pytest

from infra.litellm.config_validator import validate_config

pytestmark = pytest.mark.integration

OFFLINE_LOCAL_ENV = {
    "LITELLM_LOCAL_CHAT_MODEL": "ollama_chat/qwen3:14b",
    "LITELLM_LOCAL_EMBED_MODEL": "ollama/nomic-embed-text",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "QDRANT_API_BASE": "http://127.0.0.1:6333",
}


def test_litellm_mcp_registration_validates_offline() -> None:
    cfg = validate_config(
        __import__("pathlib").Path("infra/litellm/litellm_config.yaml"),
        env=OFFLINE_LOCAL_ENV,
        strict=False,
    )

    assert set(cfg.mcp_servers) == {
        "quimera_postgres_memory",
        "quimera_qdrant_memory",
        "quimera_working_memory",
    }
