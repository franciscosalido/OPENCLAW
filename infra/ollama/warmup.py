"""Warm up local Ollama models with explicit keep-alive."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Literal

import httpx
from loguru import logger

from infra.ollama.config import OllamaConfig, load_ollama_config


@dataclass(frozen=True, slots=True, kw_only=True)
class WarmupSpec:
    model: str
    mode: Literal["embed", "chat"]
    keep_alive: int | str
    test_input: str

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if not self.test_input.strip():
            raise ValueError("test_input cannot be empty")


MODELS_TO_WARMUP = [
    WarmupSpec(
        model="nomic-embed-text:latest",
        mode="embed",
        keep_alive=-1,
        test_input="warmup",
    ),
    WarmupSpec(
        model="qwen3:14b",
        mode="chat",
        keep_alive=-1,
        test_input="ping",
    ),
]


async def warmup_model(
    spec: WarmupSpec,
    *,
    base_url: str,
    timeout_seconds: float,
) -> bool:
    """Warm one model; return False on safe operational failure."""

    path, body = _warmup_request(spec)
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        ) as client:
            response = await client.post(path, json=body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug(
            "ollama_warmup_failed model={} mode={} error={}",
            spec.model,
            spec.mode,
            exc.__class__.__name__,
        )
        return False
    return True


async def warmup_all_models(
    config: OllamaConfig | None = None,
) -> dict[str, bool]:
    """Warm all configured models and return model -> success."""

    resolved = config or load_ollama_config()
    specs = _specs_from_config(resolved)
    results: dict[str, bool] = {}
    for spec in specs:
        results[spec.model] = await warmup_model(
            spec,
            base_url=resolved.base_url,
            timeout_seconds=resolved.warmup_timeout_seconds,
        )
    return results


def warmup_all_models_sync(config: OllamaConfig | None = None) -> dict[str, bool]:
    return asyncio.run(warmup_all_models(config))


def main() -> int:
    results = warmup_all_models_sync()
    failed = [model for model, ok in results.items() if not ok]
    if failed:
        sys.stderr.write(f"Ollama warmup failed for: {', '.join(failed)}\n")
        return 1
    sys.stdout.write("Ollama warmup OK\n")
    return 0


def _specs_from_config(config: OllamaConfig) -> list[WarmupSpec]:
    return [
        WarmupSpec(
            model=config.embed_model,
            mode="embed",
            keep_alive=config.keep_alive,
            test_input="warmup",
        ),
        WarmupSpec(
            model=config.chat_model,
            mode="chat",
            keep_alive=config.keep_alive,
            test_input="ping",
        ),
    ]


def _warmup_request(spec: WarmupSpec) -> tuple[str, dict[str, object]]:
    if spec.mode == "embed":
        return (
            "/api/embed",
            {
                "model": spec.model,
                "input": spec.test_input,
                "keep_alive": spec.keep_alive,
            },
        )
    return (
        "/api/chat",
        {
            "model": spec.model,
            "messages": [{"role": "user", "content": spec.test_input}],
            "stream": False,
            "keep_alive": spec.keep_alive,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
