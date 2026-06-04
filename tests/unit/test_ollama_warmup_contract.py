from __future__ import annotations

from typing import Any

import httpx
import pytest

from infra.ollama.config import OllamaConfig
from infra.ollama import shutdown_hook, warmup
from infra.ollama.warmup import WarmupSpec


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.request = httpx.Request("POST", "http://ollama.local")
        self.response = httpx.Response(status_code, request=self.request)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "ollama request failed",
                request=self.request,
                response=self.response,
            )


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []
    status_codes: list[int] = []

    def __init__(self, *, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, path: str, *, json: dict[str, object]) -> FakeResponse:
        self.calls.append(
            {
                "base_url": self.base_url,
                "timeout": self.timeout,
                "path": path,
                "json": json,
            }
        )
        status_code = self.status_codes.pop(0) if self.status_codes else 200
        return FakeResponse(status_code)


@pytest.fixture(autouse=True)
def reset_fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.status_codes = []
    monkeypatch.setattr("infra.ollama.warmup.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "infra.ollama.shutdown_hook.httpx.AsyncClient",
        FakeAsyncClient,
    )


@pytest.mark.asyncio
async def test_warmup_embed_calls_embed_endpoint_with_keep_alive() -> None:
    spec = WarmupSpec(
        model="nomic-embed-text:latest",
        mode="embed",
        keep_alive=-1,
        test_input="warmup",
    )

    assert await warmup.warmup_model(spec, base_url="http://ollama", timeout_seconds=3)

    call = FakeAsyncClient.calls[-1]
    assert call["path"] == "/api/embed"
    assert call["json"]["model"] == "nomic-embed-text:latest"
    assert call["json"]["input"] == "warmup"
    assert call["json"]["keep_alive"] == -1


@pytest.mark.asyncio
async def test_warmup_chat_calls_chat_endpoint_with_stream_false() -> None:
    spec = WarmupSpec(
        model="qwen3:14b",
        mode="chat",
        keep_alive=-1,
        test_input="ping",
    )

    assert await warmup.warmup_model(spec, base_url="http://ollama", timeout_seconds=3)

    call = FakeAsyncClient.calls[-1]
    assert call["path"] == "/api/chat"
    assert call["json"]["stream"] is False
    assert call["json"]["keep_alive"] == -1


@pytest.mark.asyncio
async def test_release_chat_uses_keep_alive_zero() -> None:
    spec = WarmupSpec(model="qwen3:14b", mode="chat", keep_alive=-1, test_input="ping")

    assert await shutdown_hook.release_model(
        spec,
        base_url="http://ollama",
        timeout_seconds=3,
    )

    call = FakeAsyncClient.calls[-1]
    assert call["path"] == "/api/chat"
    assert call["json"]["keep_alive"] == 0
    assert call["json"]["messages"] == []


@pytest.mark.asyncio
async def test_release_embed_uses_keep_alive_zero() -> None:
    spec = WarmupSpec(
        model="nomic-embed-text:latest",
        mode="embed",
        keep_alive=-1,
        test_input="warmup",
    )

    assert await shutdown_hook.release_model(
        spec,
        base_url="http://ollama",
        timeout_seconds=3,
    )

    call = FakeAsyncClient.calls[-1]
    assert call["path"] == "/api/embed"
    assert call["json"]["keep_alive"] == 0


@pytest.mark.asyncio
async def test_release_chat_fallback_uses_generate_with_empty_prompt() -> None:
    FakeAsyncClient.status_codes = [500, 200]
    spec = WarmupSpec(model="qwen3:14b", mode="chat", keep_alive=-1, test_input="ping")

    assert await shutdown_hook.release_model(
        spec,
        base_url="http://ollama",
        timeout_seconds=3,
    )

    assert FakeAsyncClient.calls[0]["path"] == "/api/chat"
    assert FakeAsyncClient.calls[1]["path"] == "/api/generate"
    assert FakeAsyncClient.calls[1]["json"]["prompt"] == ""
    assert FakeAsyncClient.calls[1]["json"]["keep_alive"] == 0


@pytest.mark.asyncio
async def test_warmup_and_release_all_return_dict_by_model() -> None:
    config = OllamaConfig(embed_model="embed-test", chat_model="chat-test")

    warmup_result = await warmup.warmup_all_models(config)
    release_result = await shutdown_hook.release_all_models(config)

    assert warmup_result == {"embed-test": True, "chat-test": True}
    assert release_result == {"embed-test": True, "chat-test": True}


@pytest.mark.asyncio
async def test_warmup_failure_returns_false_without_payload_leak() -> None:
    FakeAsyncClient.status_codes = [500]
    spec = WarmupSpec(model="qwen3:14b", mode="chat", keep_alive=-1, test_input="secret")

    assert not await warmup.warmup_model(
        spec,
        base_url="http://ollama",
        timeout_seconds=3,
    )
