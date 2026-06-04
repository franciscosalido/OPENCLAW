from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from infra.ollama.config import OllamaConfig, load_ollama_config
from infra.ollama.warmup import MODELS_TO_WARMUP, WarmupSpec


def test_warmup_spec_has_required_fields() -> None:
    spec = WarmupSpec(
        model="nomic-embed-text:latest",
        mode="embed",
        keep_alive=-1,
        test_input="warmup",
    )

    assert spec.model == "nomic-embed-text:latest"
    assert spec.mode == "embed"
    assert spec.keep_alive == -1
    assert spec.test_input == "warmup"


def test_models_to_warmup_include_canonical_models() -> None:
    models = {spec.model for spec in MODELS_TO_WARMUP}

    assert "nomic-embed-text:latest" in models
    assert "qwen3:14b" in models


def test_ollama_config_defaults() -> None:
    config = OllamaConfig()

    assert config.keep_alive == -1
    assert config.num_parallel == 2
    assert config.max_loaded_models == 2
    assert config.embed_model == "nomic-embed-text:latest"
    assert config.chat_model == "qwen3:14b"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_parallel": 0},
        {"max_loaded_models": 1},
        {"base_url": " "},
        {"embed_model": ""},
        {"chat_model": " "},
        {"warmup_timeout_seconds": 0},
    ],
)
def test_ollama_config_validation(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OllamaConfig(**cast(Any, kwargs))


def test_ollama_config_env_file_is_parseable() -> None:
    config = load_ollama_config(Path("infra/ollama/ollama_config.env"))

    assert config.base_url == "http://127.0.0.1:11434"
    assert config.keep_alive == -1
    assert config.num_parallel == 2
    assert config.max_loaded_models == 2


def test_real_env_overrides_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "OLLAMA_BASE_URL",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_NUM_PARALLEL",
        "OLLAMA_MAX_LOADED_MODELS",
        "QUIMERA_OLLAMA_EMBED_MODEL",
        "QUIMERA_OLLAMA_CHAT_MODEL",
        "QUIMERA_OLLAMA_WARMUP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / "ollama_config.env"
    env_file.write_text(
        "\n".join(
            (
                "OLLAMA_BASE_URL=http://file.local:11434",
                "OLLAMA_KEEP_ALIVE=30m",
                "OLLAMA_NUM_PARALLEL=1",
                "QUIMERA_OLLAMA_CHAT_MODEL=file-chat",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env.local:11434")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "-1")
    monkeypatch.setenv("QUIMERA_OLLAMA_CHAT_MODEL", "env-chat")

    config = load_ollama_config(env_file)

    assert config.base_url == "http://env.local:11434"
    assert config.keep_alive == -1
    assert config.num_parallel == 1
    assert config.chat_model == "env-chat"
