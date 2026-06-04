from __future__ import annotations

from pathlib import Path

import yaml

from infra.litellm.config_validator import CANONICAL_EMBED_DIM


CONFIG = Path("infra/litellm/litellm_config.yaml")
CHAT_ALIASES = {"local_chat", "local_think", "local_rag", "local_json"}


def _aliases() -> dict[str, dict]:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return {item["model_name"]: item for item in raw["model_list"]}


def test_local_think_timeout_is_120() -> None:
    assert _aliases()["local_think"]["litellm_params"]["timeout"] == 120


def test_embedding_timeouts_are_5_seconds() -> None:
    aliases = _aliases()

    assert aliases["nomic-embed-text"]["litellm_params"]["timeout"] == 5
    assert aliases["quimera_embed"]["litellm_params"]["timeout"] == 5
    assert aliases["local_embed"]["litellm_params"]["timeout"] == 5


def test_all_models_have_stream_timeout_and_one_retry() -> None:
    for alias, item in _aliases().items():
        params = item["litellm_params"]
        assert params["stream_timeout"] > 0, alias
        assert params["stream_timeout"] <= params["timeout"], alias
        assert params["max_retries"] == 1, alias


def test_chat_models_have_slow_start_stream_timeout_budget() -> None:
    aliases = _aliases()

    for alias in CHAT_ALIASES:
        assert aliases[alias]["litellm_params"]["stream_timeout"] == 45, alias


def test_embedding_models_keep_short_stream_timeout() -> None:
    aliases = _aliases()

    assert aliases["nomic-embed-text"]["litellm_params"]["stream_timeout"] == 5
    assert aliases["quimera_embed"]["litellm_params"]["stream_timeout"] == 5
    assert aliases["local_embed"]["litellm_params"]["stream_timeout"] == 5


def test_global_request_timeout_covers_longest_model_timeout() -> None:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)

    assert raw["litellm_settings"]["request_timeout"] == 165


def test_embedding_dimension_uses_canonical_constant() -> None:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    cache_params = raw["litellm_settings"]["cache_params"]

    assert cache_params["qdrant_semantic_cache_vector_size"] == CANONICAL_EMBED_DIM
    for alias in ("quimera_embed", "local_embed"):
        model_info = _aliases()[alias]["model_info"]
        assert model_info["output_dimensions"] == CANONICAL_EMBED_DIM
