"""Local answer generation via Ollama chat API."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from loguru import logger


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_GENERATION_MODEL = "qwen3:14b"
DEFAULT_GENERATION_TIMEOUT_SECONDS = 120.0
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GenerationError(Exception):
    """Raised when local generation returns an invalid response."""


@dataclass
class LocalGenerator:
    """Small async client for local Ollama `/api/chat` generation."""

    model: str = DEFAULT_GENERATION_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    client: httpx.AsyncClient | None = None
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")

        self.base_url = self.base_url.rstrip("/")
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
            )
            self._owns_client = True

    async def __aenter__(self) -> LocalGenerator:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP client."""

        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
    ) -> str:
        """Generate one local answer with Ollama chat API."""

        if self.client is None:
            raise RuntimeError("HTTP client is not initialized")

        clean_messages = _validate_messages(messages)
        effective_temperature = self.temperature if temperature is None else temperature
        if not 0.0 <= effective_temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": clean_messages,
            "stream": False,
            "options": {
                "temperature": effective_temperature,
                "num_predict": self.max_tokens,
            },
        }
        start = time.perf_counter()
        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        body = cast(dict[str, Any], response.json())
        answer = _extract_answer(body)
        if not thinking_mode:
            answer = _strip_thinking(answer)

        logger.debug(
            "generate | model={} chars={} latency={:.1f}ms",
            self.model,
            len(answer),
            (time.perf_counter() - start) * 1000,
        )
        return answer


def _validate_messages(messages: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        raise ValueError("messages cannot be empty")

    clean_messages: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "").strip()
        content = message.get("content", "").strip()
        if role not in {"system", "user", "assistant"}:
            raise ValueError("message role must be system, user, or assistant")
        if not content:
            raise ValueError("message content cannot be empty")
        clean_messages.append({"role": role, "content": content})
    return clean_messages


def _extract_answer(body: dict[str, Any]) -> str:
    message = body.get("message")
    if not isinstance(message, dict):
        raise GenerationError("Ollama response did not include message")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GenerationError("Ollama response message content is empty")
    return content.strip()


def _strip_thinking(answer: str) -> str:
    return _THINK_BLOCK_RE.sub("", answer).strip()
