from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from infra.litellm.config_validator import ConfigValidationError
from infra.litellm.render_config import render_runtime_config


CONFIG = Path("infra/litellm/litellm_config.yaml")


def test_renderer_falls_back_to_local_cache_without_experimental_flag(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.yaml"

    result = render_runtime_config(
        source_path=CONFIG,
        runtime_path=runtime,
        env={
            "LITELLM_MASTER_KEY": "local-dev-key",
            "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL": "0",
            "QUIMERA_LITELLM_CACHE_FALLBACK": "local",
        },
        qdrant_smoke=lambda _url: False,
    )

    rendered = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert result.cache_backend == "local"
    assert rendered["litellm_settings"]["cache_params"]["type"] == "local"


def test_renderer_keeps_qdrant_semantic_when_flag_and_qdrant_ready(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.yaml"

    result = render_runtime_config(
        source_path=CONFIG,
        runtime_path=runtime,
        env={
            "LITELLM_MASTER_KEY": "local-dev-key",
            "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL": "1",
            "QDRANT_API_BASE": "http://127.0.0.1:6333",
        },
        qdrant_smoke=lambda _url: True,
    )

    rendered = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert result.cache_backend == "qdrant-semantic"
    assert rendered["litellm_settings"]["cache_params"]["type"] == "qdrant-semantic"


def test_renderer_rejects_qdrant_without_ready_backend_when_no_fallback(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError, match="Qdrant semantic cache requested"):
        render_runtime_config(
            source_path=CONFIG,
            runtime_path=tmp_path / "runtime.yaml",
            env={
                "LITELLM_MASTER_KEY": "local-dev-key",
                "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL": "1",
                "QUIMERA_LITELLM_CACHE_FALLBACK": "none",
            },
            qdrant_smoke=lambda _url: False,
        )


def test_renderer_preserves_unicode_in_runtime_yaml(tmp_path: Path) -> None:
    source = tmp_path / "litellm_config.yaml"
    runtime = tmp_path / "runtime.yaml"
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw["model_list"][0]["model_info"]["purpose"] = "síntese local"
    source.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")

    render_runtime_config(
        source_path=source,
        runtime_path=runtime,
        env={
            "LITELLM_MASTER_KEY": "local-dev-key",
            "QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL": "0",
            "QUIMERA_LITELLM_CACHE_FALLBACK": "local",
        },
        qdrant_smoke=lambda _url: False,
    )

    runtime_text = runtime.read_text(encoding="utf-8")
    assert "síntese local" in runtime_text
    assert "\\u00ed" not in runtime_text
