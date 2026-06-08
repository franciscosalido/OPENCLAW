from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


HTTP_TIMEOUT = httpx.Timeout(connect=1.0, read=5.0, write=2.0, pool=1.0)


@dataclass(frozen=True)
class SmokeResult:
    name: str
    ok: bool
    status_code: int | None = None
    message: str = "ok"


@dataclass(frozen=True)
class SmokeSummary:
    readiness: SmokeResult
    liveliness: SmokeResult
    models: SmokeResult
    ollama: SmokeResult
    qdrant: SmokeResult
    chat: bool | None = None
    embed: bool | None = None

    @property
    def ok(self) -> bool:
        return (
            self.readiness.ok
            and self.liveliness.ok
            and self.models.ok
            and self.ollama.ok
            and self.qdrant.ok
            and self.chat is not False
            and self.embed is not False
        )


async def _get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> SmokeResult:
    try:
        result = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return SmokeResult(
            name=url.rsplit("/", 1)[-1], ok=False, message=exc.__class__.__name__
        )
    return SmokeResult(
        name=url.rsplit("/", 1)[-1],
        ok=result.status_code < 400,
        status_code=result.status_code,
    )


async def smoke_litellm_readiness(base_url: str) -> SmokeResult:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await _get_json(client, f"{base}/health/readiness")


async def smoke_litellm_liveliness(base_url: str) -> SmokeResult:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await _get_json(client, f"{base}/health/liveliness")


async def smoke_litellm_models(base_url: str, master_key: str | None) -> SmokeResult:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {master_key}"} if master_key else {}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await _get_json(client, f"{base}/v1/models", headers=headers)


async def smoke_ollama_version(base_url: str) -> SmokeResult:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await _get_json(client, f"{base}/api/version")


async def smoke_qdrant_ready(base_url: str) -> SmokeResult:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for endpoint in ("/readyz", "/healthz"):
            result = await _get_json(client, f"{base}{endpoint}")
            if result.ok:
                return SmokeResult(
                    name=endpoint.strip("/"), ok=True, status_code=result.status_code
                )
        return result


async def smoke_chat_opt_in(base_url: str, master_key: str | None) -> SmokeResult:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {master_key}"} if master_key else {}
    payload: dict[str, Any] = {
        "model": "local_chat",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=1.0, read=130.0, write=2.0, pool=1.0)
    ) as client:
        result = await client.post(
            f"{base}/v1/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
    return SmokeResult(
        name="chat", ok=result.status_code < 400, status_code=result.status_code
    )


async def smoke_embedding_opt_in(base_url: str, master_key: str | None) -> SmokeResult:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {master_key}"} if master_key else {}
    payload: dict[str, Any] = {"model": "quimera_embed", "input": "ping"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=1.0, read=20.0, write=2.0, pool=1.0)
    ) as client:
        result = await client.post(
            f"{base}/v1/embeddings",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
    return SmokeResult(
        name="embedding", ok=result.status_code < 400, status_code=result.status_code
    )


def run_smoke(
    base_url: str,
    api_key: str | None = None,
    *,
    test_chat: bool = False,
    test_embed: bool = False,
    ollama_base_url: str = "http://127.0.0.1:11434",
    qdrant_base_url: str = "http://127.0.0.1:6333",
) -> SmokeSummary:
    import asyncio

    async def _run() -> SmokeSummary:
        readiness = await smoke_litellm_readiness(base_url)
        liveliness = await smoke_litellm_liveliness(base_url)
        models = await smoke_litellm_models(base_url, api_key)
        ollama = await smoke_ollama_version(ollama_base_url)
        qdrant = await smoke_qdrant_ready(qdrant_base_url)
        chat_ok: bool | None = None
        embed_ok: bool | None = None
        if test_chat:
            chat_ok = (await smoke_chat_opt_in(base_url, api_key)).ok
        if test_embed:
            embed_ok = (await smoke_embedding_opt_in(base_url, api_key)).ok
        return SmokeSummary(
            readiness, liveliness, models, ollama, qdrant, chat_ok, embed_ok
        )

    return asyncio.run(_run())


def main() -> int:
    result = run_smoke(
        os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
        os.environ.get("QUIMERA_LLM_API_KEY") or os.environ.get("LITELLM_MASTER_KEY"),
        test_chat=os.environ.get("QUIMERA_LITELLM_TEST_CHAT") == "1",
        test_embed=os.environ.get("QUIMERA_LITELLM_TEST_EMBED") == "1",
        ollama_base_url=os.environ.get(
            "OLLAMA_BASE_URL",
            os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434"),
        ),
        qdrant_base_url=os.environ.get("QDRANT_API_BASE", "http://127.0.0.1:6333"),
    )
    sys.stdout.write(f"readiness={result.readiness.ok}\n")
    sys.stdout.write(f"liveliness={result.liveliness.ok}\n")
    sys.stdout.write(f"models={result.models.ok}\n")
    sys.stdout.write(f"ollama={result.ollama.ok}\n")
    sys.stdout.write(f"qdrant={result.qdrant.ok}\n")
    if result.chat is not None:
        sys.stdout.write(f"chat={result.chat}\n")
    if result.embed is not None:
        sys.stdout.write(f"embedding={result.embed}\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
