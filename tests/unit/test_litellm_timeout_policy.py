from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path("infra/litellm/litellm_config.yaml")


def _aliases() -> dict[str, dict]:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return {item["model_name"]: item for item in raw["model_list"]}


def test_local_think_timeout_is_120() -> None:
    assert _aliases()["local_think"]["litellm_params"]["timeout"] == 120


def test_embedding_timeouts_are_20_seconds() -> None:
    aliases = _aliases()

    assert aliases["quimera_embed"]["litellm_params"]["timeout"] == 20
    assert aliases["local_embed"]["litellm_params"]["timeout"] == 20


def test_all_models_have_stream_timeout_and_one_retry() -> None:
    for alias, item in _aliases().items():
        params = item["litellm_params"]
        assert params["stream_timeout"] > 0, alias
        assert params["max_retries"] == 1, alias


def test_global_request_timeout_covers_longest_model_timeout() -> None:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)

    assert raw["litellm_settings"]["request_timeout"] == 130
