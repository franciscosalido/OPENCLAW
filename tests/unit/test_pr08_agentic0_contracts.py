from __future__ import annotations

from integration.agentic0_contracts import (
    Agentic0SmokeConfig,
    SMOKE_SCHEMA_VERSION,
    skipped_result,
)


def test_agentic0_config_defaults_are_local_and_safe() -> None:
    cfg = Agentic0SmokeConfig()

    assert cfg.litellm_base_url == "http://127.0.0.1:4000"
    assert cfg.litellm_model == "qwen3-local"
    assert cfg.embedding_model == "nomic-embed-text"
    assert cfg.allowed_tools
    assert "*" not in cfg.allowed_tools
    assert cfg.autonomous_tool_use_enabled is False
    assert cfg.timeout_seconds > 0


def test_agentic0_result_schema_and_repr_do_not_leak() -> None:
    result = skipped_result(Agentic0SmokeConfig(), reason="unit")
    text = repr(result)

    assert result.schema_version == SMOKE_SCHEMA_VERSION
    assert result.correlation_id
    assert "prompt" not in text.lower()
    assert "chunk" not in text.lower()
    assert "vector" not in text.lower()
