from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from json import dumps
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from infra.litellm.config_validator import (
    CANONICAL_QDRANT_BASE_URL,
    ConfigValidationError,
    load_raw_config,
    smoke_test_qdrant_sync,
    validate_litellm_config,
)


@dataclass(frozen=True)
class RenderResult:
    source_path: Path
    runtime_path: Path
    cache_backend: str
    fallback_active: bool = False


def _qdrant_url(cache_params: dict[str, Any], env: Mapping[str, str]) -> str:
    value = str(cache_params.get("qdrant_api_base") or "os.environ/QDRANT_API_BASE")
    if value.startswith("os.environ/"):
        key = value.removeprefix("os.environ/")
        return env.get(key, CANONICAL_QDRANT_BASE_URL)
    return value


def _write_safe_event(
    repo_root: Path, *, status: str, cache_backend: str, fallback_active: bool
) -> None:
    event_dir = repo_root / ".runtime" / "events"
    event_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "event.name": "litellm.config.render",
        "service.name": "quimera_litellm_host",
        "quimera.component": "litellm",
        "quimera.stage": "render_config",
        "status": status,
        "cache.backend": cache_backend,
        "cache.fallback_active": fallback_active,
        "version.schema": "quimera-safe-event-v1",
        "created_at": datetime.now(UTC).isoformat(),
    }
    with (event_dir / "litellm_render.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(dumps(event, sort_keys=True) + "\n")


def render_runtime_config(
    *,
    source_path: Path,
    runtime_path: Path,
    env: Mapping[str, str] | None = None,
    qdrant_smoke: Callable[[str], bool] | None = None,
    strict: bool = False,
) -> RenderResult:
    env_map = os.environ if env is None else env
    validate_litellm_config(source_path, env=env_map)
    rendered = load_raw_config(source_path)
    settings = rendered.setdefault("litellm_settings", {})
    general_settings = rendered.setdefault("general_settings", {})
    if "json_logs" in general_settings:
        settings.setdefault("json_logs", general_settings.pop("json_logs"))
    cache_params = settings.setdefault("cache_params", {})
    cache_backend = str(cache_params.get("type", "local"))
    fallback_active = False

    if cache_backend == "qdrant-semantic":
        qdrant_url = _qdrant_url(cache_params, env_map)
        experimental = (
            env_map.get("QUIMERA_LITELLM_QDRANT_SEMANTIC_EXPERIMENTAL") == "1"
        )
        fallback = env_map.get("QUIMERA_LITELLM_CACHE_FALLBACK", "local")
        is_ready = experimental and (qdrant_smoke or smoke_test_qdrant_sync)(qdrant_url)
        if experimental and is_ready:
            cache_backend = "qdrant-semantic"
        elif fallback in {"local", "in-memory"}:
            cache_backend = "local"
            if fallback == "in-memory":
                cache_backend = "in-memory"
            settings["cache_params"] = {"type": "local"}
            if cache_backend == "in-memory":
                settings["cache_params"] = {"type": "in-memory"}
            settings["cache_policy"] = {
                "qdrant_semantic_status": "disabled_by_policy_or_unavailable",
                "fallback_active": True,
            }
            fallback_active = True
        else:
            raise ConfigValidationError(
                "Qdrant semantic cache requested, but Qdrant is unavailable and fallback is disabled"
            )

    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_text = yaml.safe_dump(rendered, sort_keys=False, allow_unicode=True)
    master_key = env_map.get("LITELLM_MASTER_KEY")
    if master_key and master_key in runtime_text:
        raise ConfigValidationError(
            "runtime config would contain literal LITELLM_MASTER_KEY"
        )
    runtime_path.write_text(
        runtime_text,
        encoding="utf-8",
    )
    repo_root = (
        source_path.resolve().parents[2]
        if len(source_path.resolve().parents) >= 3
        else Path.cwd()
    )
    _write_safe_event(
        repo_root,
        status="ok",
        cache_backend=cache_backend,
        fallback_active=fallback_active,
    )
    return RenderResult(
        source_path=source_path,
        runtime_path=runtime_path,
        cache_backend=cache_backend,
        fallback_active=fallback_active,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    source = Path(
        os.environ.get("QUIMERA_LITELLM_CONFIG", "infra/litellm/litellm_config.yaml")
    )
    runtime = Path(
        os.environ.get(
            "QUIMERA_LITELLM_RUNTIME_CONFIG",
            "infra/litellm/generated/litellm_config.runtime.yaml",
        )
    )
    strict = False
    while args:
        arg = args.pop(0)
        if arg == "--source":
            source = Path(args.pop(0))
        elif arg == "--output":
            runtime = Path(args.pop(0))
        elif arg == "--strict":
            strict = True
        else:
            sys.stderr.write(f"unknown argument: {arg}\n")
            return 2
    try:
        result = render_runtime_config(
            source_path=source, runtime_path=runtime, strict=strict
        )
    except ConfigValidationError as exc:
        sys.stderr.write(f"render=failed\nmessage={exc}\n")
        return 1
    sys.stdout.write(f"source_path={result.source_path}\n")
    sys.stdout.write(f"runtime_path={result.runtime_path}\n")
    sys.stdout.write(f"cache_backend={result.cache_backend}\n")
    sys.stdout.write(f"fallback_active={result.fallback_active}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
