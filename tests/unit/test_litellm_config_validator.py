from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from infra.litellm.config_validator import (
    ConfigValidationError,
    assert_host_local_qdrant_url,
    load_raw_config,
    validate_litellm_config,
    validate_no_literal_secrets,
)


CONFIG = Path("infra/litellm/litellm_config.yaml")


def test_load_raw_config_loads_yaml_mapping() -> None:
    raw = load_raw_config(CONFIG)

    assert isinstance(raw, dict)
    assert "model_list" in raw
    assert "litellm_settings" in raw


def test_validate_litellm_config_accepts_project_env_refs() -> None:
    cfg = validate_litellm_config(CONFIG, env={"LITELLM_MASTER_KEY": "local-dev-key"})

    assert cfg.litellm_settings.cache is True
    assert cfg.litellm_settings.cache_params is not None
    assert cfg.litellm_settings.cache_params.qdrant_collection_name == "quimera_llm_cache"
    assert cfg.general_settings.master_key == "os.environ/LITELLM_MASTER_KEY"


def test_validate_no_literal_secrets_rejects_plain_master_key() -> None:
    with pytest.raises(ConfigValidationError, match="literal secret"):
        validate_no_literal_secrets("general_settings:\n  master_key: sk-plain-text\n")


def test_qdrant_url_must_be_loopback_http() -> None:
    assert_host_local_qdrant_url("http://127.0.0.1:6333")
    assert_host_local_qdrant_url("http://localhost:6333")

    with pytest.raises(ConfigValidationError, match="local loopback"):
        assert_host_local_qdrant_url("https://qdrant.example.com")


def test_remote_provider_models_are_rejected(tmp_path: Path) -> None:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw["model_list"][0]["litellm_params"]["model"] = "openai/gpt-5"
    bad_config = tmp_path / "bad_litellm.yaml"
    bad_config.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="remote provider"):
        validate_litellm_config(bad_config, env={"LITELLM_MASTER_KEY": "local-dev-key"})
