from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path("infra/litellm/litellm_config.yaml")


def _load_config() -> dict:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _aliases() -> dict[str, dict]:
    return {item["model_name"]: item for item in _load_config()["model_list"]}


def test_config_is_valid_yaml() -> None:
    cfg = _load_config()

    assert "model_list" in cfg
    assert "litellm_settings" in cfg
    assert "general_settings" in cfg


def test_cache_type_is_qdrant_semantic_in_source_config() -> None:
    cfg = _load_config()

    assert cfg["litellm_settings"]["cache"] is True
    assert cfg["litellm_settings"]["cache_params"]["type"] == "qdrant-semantic"


def test_cache_collection_is_separated_from_retrieval_cache() -> None:
    cache_params = _load_config()["litellm_settings"]["cache_params"]

    assert cache_params["qdrant_collection_name"] == "quimera_llm_cache"
    assert cache_params["qdrant_collection_name"] != "quimera_query_cache"


def test_models_have_loopback_ollama_env_api_base() -> None:
    for model in _load_config()["model_list"]:
        assert model["litellm_params"]["api_base"] == "os.environ/OLLAMA_BASE_URL"


def test_embedding_alias_is_used_for_semantic_cache() -> None:
    cache_params = _load_config()["litellm_settings"]["cache_params"]

    assert cache_params["qdrant_semantic_cache_embedding_model"] == "nomic-embed-text"
    assert cache_params["qdrant_semantic_cache_vector_size"] == 768
    assert "quimera_embed" in _aliases()
    assert "nomic-embed-text" in _aliases()
