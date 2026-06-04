from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from infra.litellm.config_validator import (
    load_raw_config,
    smoke_test_qdrant_sync,
    validate_litellm_config,
)


@dataclass(frozen=True)
class RenderResult:
    source_path: Path
    runtime_path: Path
    cache_backend: str


def _qdrant_url(cache_params: dict[str, Any], env: Mapping[str, str]) -> str:
    value = str(cache_params.get("qdrant_api_base") or "os.environ/QDRANT_API_BASE")
    if value.startswith("os.environ/"):
        key = value.removeprefix("os.environ/")
        return env.get(key, "http://127.0.0.1:6333")
    return value


def render_runtime_config(
    *,
    source_path: Path,
    runtime_path: Path,
    env: Mapping[str, str] | None = None,
    qdrant_smoke: Callable[[str], bool] | None = None,
) -> RenderResult:
    env_map = os.environ if env is None else env
    validate_litellm_config(source_path, env=env_map)
    rendered = load_raw_config(source_path)
    settings = rendered.setdefault("litellm_settings", {})
    cache_params = settings.setdefault("cache_params", {})
    cache_backend = str(cache_params.get("type", "local"))

    if cache_backend == "qdrant-semantic":
        qdrant_url = _qdrant_url(cache_params, env_map)
        experimental = env_map.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") == "1"
        fallback = env_map.get("QUIMERA_LITELLM_CACHE_FALLBACK", "local")
        is_ready = (qdrant_smoke or smoke_test_qdrant_sync)(qdrant_url)
        if experimental and is_ready:
            cache_backend = "qdrant-semantic"
        elif fallback == "local":
            cache_backend = "local"
            settings["cache_params"] = {"type": "local"}
        else:
            raise RuntimeError(
                "Qdrant semantic cache requested, but Qdrant is unavailable and fallback is disabled"
            )

    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        yaml.safe_dump(rendered, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return RenderResult(source_path=source_path, runtime_path=runtime_path, cache_backend=cache_backend)


def main() -> int:
    source = Path(os.environ.get("QUIMERA_LITELLM_CONFIG", "infra/litellm/litellm_config.yaml"))
    runtime = Path(
        os.environ.get(
            "QUIMERA_LITELLM_RUNTIME_CONFIG",
            "infra/litellm/generated/litellm_config.runtime.yaml",
        )
    )
    result = render_runtime_config(source_path=source, runtime_path=runtime)
    sys.stdout.write(f"source_path={result.source_path}\n")
    sys.stdout.write(f"runtime_path={result.runtime_path}\n")
    sys.stdout.write(f"cache_backend={result.cache_backend}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
