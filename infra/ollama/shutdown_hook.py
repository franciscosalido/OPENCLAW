"""Release local Ollama models with keep_alive=0."""

from __future__ import annotations

import asyncio
import sys

import httpx
from loguru import logger

from infra.ollama.config import OllamaConfig, load_ollama_config
from infra.ollama.warmup import WarmupSpec


async def release_model(
    spec: WarmupSpec,
    *,
    base_url: str,
    timeout_seconds: float,
) -> bool:
    """Release one model. Failures are reported as False for graceful stop."""

    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        ) as client:
            if spec.mode == "embed":
                response = await client.post(
                    "/api/embed",
                    json={
                        "model": spec.model,
                        "input": "release",
                        "keep_alive": 0,
                    },
                )
                response.raise_for_status()
                return True
            try:
                response = await client.post(
                    "/api/chat",
                    json={
                        "model": spec.model,
                        "messages": [],
                        "stream": False,
                        "keep_alive": 0,
                    },
                )
                response.raise_for_status()
                return True
            except httpx.HTTPError:
                fallback = await client.post(
                    "/api/generate",
                    json={
                        "model": spec.model,
                        "prompt": "",
                        "stream": False,
                        "keep_alive": 0,
                    },
                )
                fallback.raise_for_status()
                return True
    except httpx.HTTPError as exc:
        logger.debug(
            "ollama_release_failed model={} mode={} error={}",
            spec.model,
            spec.mode,
            exc.__class__.__name__,
        )
        return False


async def release_all_models(
    config: OllamaConfig | None = None,
) -> dict[str, bool]:
    resolved = config or load_ollama_config()
    specs = [
        WarmupSpec(
            model=resolved.embed_model,
            mode="embed",
            keep_alive=resolved.keep_alive,
            test_input="warmup",
        ),
        WarmupSpec(
            model=resolved.chat_model,
            mode="chat",
            keep_alive=resolved.keep_alive,
            test_input="ping",
        ),
    ]
    results: dict[str, bool] = {}
    for spec in specs:
        results[spec.model] = await release_model(
            spec,
            base_url=resolved.base_url,
            timeout_seconds=resolved.warmup_timeout_seconds,
        )
    return results


def release_all_models_sync(config: OllamaConfig | None = None) -> dict[str, bool]:
    return asyncio.run(release_all_models(config))


def main() -> int:
    results = release_all_models_sync()
    failed = [model for model, ok in results.items() if not ok]
    if failed:
        sys.stderr.write(f"Ollama release failed for: {', '.join(failed)}\n")
        return 1
    sys.stdout.write("Ollama release OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
