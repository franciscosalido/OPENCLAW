"""Local answer generation through the LiteLLM gateway."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
from loguru import logger

from backend.gateway.client import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    GatewayChatClient,
    GatewayRuntimeConfig,
)
from backend.gateway.messages import validate_chat_messages


DEFAULT_GENERATION_BASE_URL = DEFAULT_LLM_BASE_URL
DEFAULT_GENERATION_MODEL = DEFAULT_LLM_MODEL
DEFAULT_GENERATION_TIMEOUT_SECONDS = 120.0
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GenerationError(Exception):
    """Raised when local generation returns an invalid response."""


@dataclass
class LocalGenerator:
    """Small async generator backed by the local LiteLLM gateway."""

    model: str = DEFAULT_GENERATION_MODEL
    base_url: str = DEFAULT_GENERATION_BASE_URL
    api_key: str | None = None
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    client: httpx.AsyncClient | None = None
    gateway_client: GatewayChatClient | None = None
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")

        env_config = GatewayRuntimeConfig.from_env()
        effective_model = (
            env_config.default_model
            if self.model == DEFAULT_GENERATION_MODEL
            else self.model
        )
        effective_base_url = (
            env_config.base_url
            if self.base_url == DEFAULT_GENERATION_BASE_URL
            else self.base_url
        )
        if not effective_model.strip():
            raise ValueError("model cannot be empty")

        # Validate BEFORE creating any HTTP resource so that a bad api_key
        # raises GatewayAuthenticationError immediately — no client leaks.
        runtime_config = GatewayRuntimeConfig(
            base_url=effective_base_url,
            api_key=self.api_key if self.api_key is not None else env_config.api_key,
            default_model=effective_model,
            timeout_seconds=self.timeout_seconds,
        ).validated()

        if self.gateway_client is None:
            self.model = runtime_config.default_model
            self.base_url = runtime_config.base_url  # already normalised by validated()
            active_client = self.client or httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
            )
            self.gateway_client = GatewayChatClient(
                config=runtime_config,
                client=active_client,
            )
            self._owns_client = self.client is None
            self.client = active_client

    async def __aenter__(self) -> LocalGenerator:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP client."""

        if self.gateway_client is not None:
            await self.gateway_client.aclose()
        elif self._owns_client and self.client is not None:
            await self.client.aclose()

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
    ) -> str:
        """Generate one local answer through LiteLLM chat completions."""

        if self.gateway_client is None:
            raise RuntimeError("Gateway client is not initialized")

        clean_messages = validate_chat_messages(messages)
        effective_temperature = self.temperature if temperature is None else temperature
        if not 0.0 <= effective_temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")

        start = time.perf_counter()
        answer = await self.gateway_client.chat_completion(
            clean_messages,
            model=self.model,
            temperature=effective_temperature,
            max_tokens=self.max_tokens,
        )
        if not thinking_mode:
            answer = _strip_thinking(answer)

        logger.debug(
            "generate | model={} chars={} latency={:.1f}ms",
            self.model,
            len(answer),
            (time.perf_counter() - start) * 1000,
        )
        return answer


def _strip_thinking(answer: str) -> str:
    return _THINK_BLOCK_RE.sub("", answer).strip()
