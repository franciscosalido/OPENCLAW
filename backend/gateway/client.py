"""OpenAI-compatible client for the local LiteLLM gateway."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from loguru import logger

from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConfigurationError,
    GatewayConnectionError,
    GatewayResponseError,
    GatewayTimeoutError,
)
from backend.gateway.messages import validate_chat_messages


DEFAULT_LLM_BASE_URL = "http://127.0.0.1:4000/v1"
DEFAULT_LLM_MODEL = "local_chat"
DEFAULT_LLM_REASONING_MODEL = "local_think"
DEFAULT_LLM_RAG_MODEL = "local_rag"
DEFAULT_LLM_JSON_MODEL = "local_json"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
DEFAULT_LLM_EMBED_MODEL = "quimera_embed"
COMPAT_LLM_EMBED_MODEL = "local_embed"
# Python-side HTTPX timeouts are the first line of defense. LiteLLM-side
# timeouts in config/litellm_config.yaml may differ intentionally.
DEFAULT_LLM_ALIAS_TIMEOUTS: Mapping[str, float] = {
    DEFAULT_LLM_MODEL: 30.0,
    DEFAULT_LLM_REASONING_MODEL: 120.0,
    DEFAULT_LLM_RAG_MODEL: 60.0,
    DEFAULT_LLM_JSON_MODEL: 30.0,
    DEFAULT_LLM_EMBED_MODEL: 30.0,
    COMPAT_LLM_EMBED_MODEL: 30.0,
}

ENV_LLM_BASE_URL = "QUIMERA_LLM_BASE_URL"
ENV_LLM_API_KEY = "QUIMERA_LLM_API_KEY"
ENV_LLM_MODEL = "QUIMERA_LLM_MODEL"
ENV_LLM_REASONING_MODEL = "QUIMERA_LLM_REASONING_MODEL"
ENV_LLM_RAG_MODEL = "QUIMERA_LLM_RAG_MODEL"
ENV_LLM_JSON_MODEL = "QUIMERA_LLM_JSON_MODEL"

_LOCAL_BASE_PREFIXES = ("http://127.0.0.1:", "http://localhost:")


@dataclass(frozen=True)
class GatewayRuntimeConfig:
    """Runtime configuration for OpenClaw -> LiteLLM model calls."""

    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: str | None = None
    default_model: str = DEFAULT_LLM_MODEL
    reasoning_model: str = DEFAULT_LLM_REASONING_MODEL
    rag_model: str = DEFAULT_LLM_RAG_MODEL
    json_model: str = DEFAULT_LLM_JSON_MODEL
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    per_alias_timeouts: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_LLM_ALIAS_TIMEOUTS)
    )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> GatewayRuntimeConfig:
        """Load runtime gateway settings from environment variables."""
        values = os.environ if env is None else env
        return cls(
            base_url=values.get(ENV_LLM_BASE_URL, DEFAULT_LLM_BASE_URL),
            api_key=values.get(ENV_LLM_API_KEY),
            default_model=values.get(ENV_LLM_MODEL, DEFAULT_LLM_MODEL),
            reasoning_model=values.get(
                ENV_LLM_REASONING_MODEL,
                DEFAULT_LLM_REASONING_MODEL,
            ),
            rag_model=values.get(ENV_LLM_RAG_MODEL, DEFAULT_LLM_RAG_MODEL),
            json_model=values.get(ENV_LLM_JSON_MODEL, DEFAULT_LLM_JSON_MODEL),
        )

    def validated(self) -> GatewayRuntimeConfig:
        """Return a normalized config or raise a clear setup error."""
        base_url = self.base_url.rstrip("/")
        global_timeout = _validate_timeout(
            self.timeout_seconds,
            label="timeout_seconds",
        )
        validated_alias_timeouts = {
            alias.strip(): _validate_timeout(timeout, label=f"timeout for {alias!r}")
            for alias, timeout in self.per_alias_timeouts.items()
        }
        if any(not alias for alias in validated_alias_timeouts):
            raise GatewayConfigurationError("Gateway timeout alias cannot be empty")
        if not any(base_url.startswith(prefix) for prefix in _LOCAL_BASE_PREFIXES):
            raise GatewayConfigurationError(
                "QUIMERA_LLM_BASE_URL must point to the local LiteLLM gateway "
                f"at {DEFAULT_LLM_BASE_URL}. Got: {base_url!r}"
            )
        if not self.api_key or not self.api_key.strip():
            raise GatewayAuthenticationError(
                "QUIMERA_LLM_API_KEY is required and should match the local "
                "LITELLM_MASTER_KEY."
            )
        for label, alias in {
            ENV_LLM_MODEL: self.default_model,
            ENV_LLM_REASONING_MODEL: self.reasoning_model,
            ENV_LLM_RAG_MODEL: self.rag_model,
            ENV_LLM_JSON_MODEL: self.json_model,
        }.items():
            if not alias.strip():
                raise GatewayConfigurationError(f"{label} cannot be empty")

        return GatewayRuntimeConfig(
            base_url=base_url,
            api_key=self.api_key.strip(),
            default_model=self.default_model.strip(),
            reasoning_model=self.reasoning_model.strip(),
            rag_model=self.rag_model.strip(),
            json_model=self.json_model.strip(),
            timeout_seconds=global_timeout,
            per_alias_timeouts=validated_alias_timeouts,
        )

    def resolve_timeout(self, model_alias: str | None) -> float:
        """Return the request timeout for *model_alias* or the global fallback."""
        if model_alias is None:
            return self.timeout_seconds
        alias = model_alias.strip()
        return self.per_alias_timeouts.get(alias, self.timeout_seconds)


@dataclass
class GatewayChatClient:
    """Small async client for LiteLLM OpenAI-compatible chat completions."""

    config: GatewayRuntimeConfig = field(
        default_factory=lambda: GatewayRuntimeConfig.from_env().validated()
    )
    client: httpx.AsyncClient | None = None
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.config = self.config.validated()
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
            self._owns_client = True

    async def __aenter__(self) -> GatewayChatClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def chat_completion(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: Mapping[str, object] | None = None,
    ) -> str:
        """Call ``/chat/completions`` and return normalized assistant text."""
        if self.client is None:
            raise GatewayConnectionError("Gateway HTTP client is not initialized")

        model_alias = (model or self.config.default_model).strip()
        if not model_alias:
            raise GatewayConfigurationError("Gateway model alias cannot be empty")

        payload: dict[str, Any] = {
            "model": model_alias,
            "messages": validate_chat_messages(messages),
        }
        if temperature is not None:
            if not 0.0 <= temperature <= 2.0:
                raise ValueError("temperature must be between 0.0 and 2.0")
            payload["temperature"] = temperature
        if max_tokens is not None:
            if max_tokens <= 0:
                raise ValueError("max_tokens must be greater than zero")
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = dict(response_format)

        start = time.perf_counter()
        base_url_host = _base_url_host(self.config.base_url)
        request_timeout = self.config.resolve_timeout(model_alias)
        try:
            response = await self.client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=request_timeout,
            )
        except httpx.TimeoutException as exc:
            _log_gateway_call(
                model_alias=model_alias,
                base_url_host=base_url_host,
                started_at=start,
                timeout_s=request_timeout,
                status="failure",
                error_category="timeout",
            )
            raise GatewayTimeoutError(
                "Timed out calling local LiteLLM gateway.",
                alias=model_alias,
            ) from exc
        except httpx.RequestError as exc:
            _log_gateway_call(
                model_alias=model_alias,
                base_url_host=base_url_host,
                started_at=start,
                timeout_s=request_timeout,
                status="failure",
                error_category="connection",
            )
            raise GatewayConnectionError(
                "Could not reach local LiteLLM gateway. "
                "Start infra/litellm/start_litellm.sh and verify /v1/models.",
                alias=model_alias,
            ) from exc

        if response.status_code in {401, 403}:
            _log_gateway_call(
                model_alias=model_alias,
                base_url_host=base_url_host,
                started_at=start,
                timeout_s=request_timeout,
                status="failure",
                error_category="authentication",
            )
            raise GatewayAuthenticationError(
                "LiteLLM gateway authentication failed. "
                "QUIMERA_LLM_API_KEY should match LITELLM_MASTER_KEY.",
                alias=model_alias,
            )
        if response.status_code >= 400:
            _log_gateway_call(
                model_alias=model_alias,
                base_url_host=base_url_host,
                started_at=start,
                timeout_s=request_timeout,
                status="failure",
                error_category=f"http_{response.status_code}",
            )
            raise GatewayResponseError(
                f"LiteLLM gateway returned HTTP {response.status_code}.",
                alias=model_alias,
            )

        try:
            body = cast(dict[str, Any], response.json())
        except ValueError as exc:
            raise GatewayResponseError(
                "LiteLLM gateway returned invalid JSON.",
                alias=model_alias,
            ) from exc
        answer = _extract_assistant_text(body, alias=model_alias)
        _log_gateway_call(
            model_alias=model_alias,
            base_url_host=base_url_host,
            started_at=start,
            timeout_s=request_timeout,
            status="success",
            error_category=None,
        )
        return answer


def _extract_assistant_text(body: dict[str, Any], *, alias: str) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GatewayResponseError(
            "LiteLLM response did not include choices.",
            alias=alias,
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise GatewayResponseError("LiteLLM response choice is invalid.", alias=alias)
    message = first.get("message")
    if not isinstance(message, dict):
        raise GatewayResponseError(
            "LiteLLM response choice did not include a message.",
            alias=alias,
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GatewayResponseError(
            "LiteLLM response message content is empty.",
            alias=alias,
        )
    return content.strip()


def _base_url_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or "unknown"


def _validate_timeout(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GatewayConfigurationError(
            f"Gateway {label} must be a finite number greater than zero"
        )
    timeout = float(value)
    if not isfinite(timeout) or timeout <= 0:
        raise GatewayConfigurationError(
            f"Gateway {label} must be a finite number greater than zero"
        )
    return timeout


def _log_gateway_call(
    *,
    model_alias: str,
    base_url_host: str,
    started_at: float,
    timeout_s: float,
    status: str,
    error_category: str | None,
) -> None:
    logger.debug(
        "gateway_call | model_alias={} base_url_host={} latency_ms={:.1f} "
        "timeout_s={:.1f} status={} error_category={}",
        model_alias,
        base_url_host,
        (time.perf_counter() - started_at) * 1000,
        timeout_s,
        status,
        error_category or "none",
    )
