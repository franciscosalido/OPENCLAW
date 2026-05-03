from __future__ import annotations

import json
import unittest
from math import inf, nan
from pathlib import Path
from typing import cast

import httpx
import yaml
from loguru import logger

from backend.gateway.client import (
    COMPAT_LLM_EMBED_MODEL,
    DEFAULT_LLM_ALIAS_TIMEOUTS,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_EMBED_MODEL,
    DEFAULT_LLM_JSON_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_RAG_MODEL,
    DEFAULT_LLM_REASONING_MODEL,
    GatewayChatClient,
    GatewayRuntimeConfig,
)
from backend.gateway.errors import (
    GatewayAuthenticationError,
    GatewayConfigurationError,
    GatewayConnectionError,
    GatewayResponseError,
)


class GatewayRuntimeConfigTests(unittest.TestCase):
    def test_defaults_point_to_local_litellm_aliases(self) -> None:
        config = GatewayRuntimeConfig(api_key="dev-key").validated()

        self.assertEqual(config.base_url, "http://127.0.0.1:4000/v1")
        self.assertEqual(config.default_model, "local_chat")
        self.assertEqual(config.reasoning_model, "local_think")
        self.assertEqual(config.rag_model, "local_rag")
        self.assertEqual(config.json_model, "local_json")

    def test_default_alias_timeouts_are_concrete(self) -> None:
        config = GatewayRuntimeConfig(api_key="dev-key").validated()

        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_MODEL), 30.0)
        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_REASONING_MODEL), 120.0)
        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_RAG_MODEL), 60.0)
        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_JSON_MODEL), 30.0)
        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_EMBED_MODEL), 30.0)

    def test_unknown_alias_and_none_fall_back_to_global_timeout(self) -> None:
        config = GatewayRuntimeConfig(
            api_key="dev-key",
            timeout_seconds=77.0,
        ).validated()

        self.assertEqual(config.resolve_timeout("local_unknown"), 77.0)
        self.assertEqual(config.resolve_timeout(None), 77.0)

    def test_empty_per_alias_timeouts_keeps_global_fallback(self) -> None:
        config = GatewayRuntimeConfig(
            api_key="dev-key",
            timeout_seconds=42.0,
            per_alias_timeouts={},
        ).validated()

        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_MODEL), 42.0)

    def test_custom_per_alias_timeout_overrides_default(self) -> None:
        config = GatewayRuntimeConfig(
            api_key="dev-key",
            timeout_seconds=42.0,
            per_alias_timeouts={DEFAULT_LLM_MODEL: 12.0},
        ).validated()

        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_MODEL), 12.0)
        self.assertEqual(config.resolve_timeout(DEFAULT_LLM_RAG_MODEL), 42.0)

    def test_default_alias_timeout_mapping_matches_contract(self) -> None:
        self.assertEqual(
            dict(DEFAULT_LLM_ALIAS_TIMEOUTS),
            {
                DEFAULT_LLM_MODEL: 30.0,
                DEFAULT_LLM_REASONING_MODEL: 120.0,
                DEFAULT_LLM_RAG_MODEL: 60.0,
                DEFAULT_LLM_JSON_MODEL: 30.0,
                DEFAULT_LLM_EMBED_MODEL: 30.0,
                COMPAT_LLM_EMBED_MODEL: 30.0,
            },
        )

    def test_global_timeout_must_be_positive_and_finite(self) -> None:
        for timeout in (0.0, -1.0, inf, nan):
            with self.subTest(timeout=timeout):
                with self.assertRaises(GatewayConfigurationError):
                    GatewayRuntimeConfig(
                        api_key="dev-key",
                        timeout_seconds=timeout,
                    ).validated()

    def test_per_alias_timeout_must_be_positive_and_finite(self) -> None:
        for timeout in (0.0, -1.0, inf, nan):
            with self.subTest(timeout=timeout):
                with self.assertRaises(GatewayConfigurationError):
                    GatewayRuntimeConfig(
                        api_key="dev-key",
                        per_alias_timeouts={DEFAULT_LLM_MODEL: timeout},
                    ).validated()

    def test_empty_timeout_alias_is_rejected(self) -> None:
        with self.assertRaises(GatewayConfigurationError):
            GatewayRuntimeConfig(
                api_key="dev-key",
                per_alias_timeouts={" ": 30.0},
            ).validated()

    def test_default_constants_do_not_include_vendor_model_names(self) -> None:
        defaults = [
            DEFAULT_LLM_BASE_URL,
            DEFAULT_LLM_MODEL,
            DEFAULT_LLM_REASONING_MODEL,
            DEFAULT_LLM_RAG_MODEL,
            DEFAULT_LLM_JSON_MODEL,
        ]

        forbidden = ("qwen", "qwen3", "llama", "ollama/", "gpt", "claude", "gemini")
        for value in defaults:
            with self.subTest(value=value):
                lowered = value.lower()
                self.assertFalse(any(name in lowered for name in forbidden))

    def test_rag_generation_config_uses_semantic_aliases(self) -> None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "rag_config.yaml"
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        generation = raw["rag"]["generation"]

        self.assertEqual(generation["endpoint"], DEFAULT_LLM_BASE_URL)
        self.assertEqual(generation["model"], DEFAULT_LLM_RAG_MODEL)
        self.assertEqual(generation["reasoning_model"], DEFAULT_LLM_REASONING_MODEL)
        self.assertEqual(generation["json_model"], DEFAULT_LLM_JSON_MODEL)
        for key in ("model", "reasoning_model", "json_model", "endpoint"):
            value = str(generation[key]).lower()
            self.assertNotIn("qwen", value)
            self.assertNotIn("ollama/", value)

    def test_remote_base_url_is_rejected(self) -> None:
        with self.assertRaises(GatewayConfigurationError):
            GatewayRuntimeConfig(
                base_url="https://api.openai.com/v1",
                api_key="dev-key",
            ).validated()

    def test_missing_api_key_raises_authentication_error_without_secret(self) -> None:
        with self.assertRaises(GatewayAuthenticationError) as ctx:
            GatewayRuntimeConfig(api_key=None).validated()

        self.assertNotIn("dev-key", str(ctx.exception))
        self.assertIn("QUIMERA_LLM_API_KEY", str(ctx.exception))


class GatewayChatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_completion_posts_openai_compatible_payload(self) -> None:
        seen_payloads: list[dict[str, object]] = []
        seen_auth_headers: list[str | None] = []
        seen_timeouts: list[dict[str, float]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            seen_auth_headers.append(request.headers.get("authorization"))
            seen_timeouts.append(cast("dict[str, float]", request.extensions["timeout"]))
            self.assertEqual(request.url.path, "/v1/chat/completions")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resposta compacta."}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="secret-test-key"),
                client=client,
            )
            answer = await gateway.chat_completion(
                [{"role": "user", "content": "pergunta"}],
                temperature=0.1,
                max_tokens=64,
            )

        self.assertEqual(answer, "Resposta compacta.")
        self.assertEqual(seen_auth_headers, ["Bearer secret-test-key"])
        self.assertEqual(seen_timeouts[0]["read"], 30.0)
        self.assertEqual(
            seen_payloads,
            [
                {
                    "model": "local_chat",
                    "messages": [{"role": "user", "content": "pergunta"}],
                    "temperature": 0.1,
                    "max_tokens": 64,
                }
            ],
        )

    async def test_chat_completion_omits_max_tokens_when_none(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resposta compacta."}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="secret-test-key"),
                client=client,
            )
            answer = await gateway.chat_completion(
                [{"role": "user", "content": "pergunta"}],
                max_tokens=None,
            )

        self.assertEqual(answer, "Resposta compacta.")
        self.assertNotIn("max_tokens", seen_payloads[0])

    async def test_chat_completion_uses_alias_specific_timeout(self) -> None:
        seen_timeouts: list[dict[str, float]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_timeouts.append(cast("dict[str, float]", request.extensions["timeout"]))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            await gateway.chat_completion(
                [{"role": "user", "content": "pergunta"}],
                model=DEFAULT_LLM_REASONING_MODEL,
            )
            await gateway.chat_completion(
                [{"role": "user", "content": "pergunta"}],
                model=DEFAULT_LLM_RAG_MODEL,
            )

        self.assertEqual(seen_timeouts[0]["read"], 120.0)
        self.assertEqual(seen_timeouts[1]["read"], 60.0)

    async def test_gateway_log_includes_timeout_without_prompt_or_secret(self) -> None:
        logs: list[str] = []
        sink_id = logger.add(
            lambda message: logs.append(str(message)),
            format="{message}",
        )
        try:
            async with httpx.AsyncClient(
                base_url=DEFAULT_LLM_BASE_URL,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        json={"choices": [{"message": {"content": "ok"}}]},
                    )
                ),
            ) as client:
                gateway = GatewayChatClient(
                    config=GatewayRuntimeConfig(api_key="secret-test-key"),
                    client=client,
                )
                await gateway.chat_completion(
                    [{"role": "user", "content": "prompt sintetico secreto"}],
                    model=DEFAULT_LLM_RAG_MODEL,
                )
        finally:
            logger.remove(sink_id)

        joined = "\n".join(logs)
        self.assertIn("timeout_s=60.0", joined)
        self.assertIn("model_alias=local_rag", joined)
        self.assertNotIn("secret-test-key", joined)
        self.assertNotIn("prompt sintetico secreto", joined)

    async def test_authentication_failure_does_not_print_api_key(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(lambda _request: httpx.Response(401)),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="secret-test-key"),
                client=client,
            )
            with self.assertRaises(GatewayAuthenticationError) as ctx:
                await gateway.chat_completion([{"role": "user", "content": "pergunta"}])

        self.assertNotIn("secret-test-key", str(ctx.exception))
        self.assertIn("authentication failed", str(ctx.exception))

    async def test_connection_failure_raises_domain_exception(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayConnectionError) as ctx:
                await gateway.chat_completion([{"role": "user", "content": "pergunta"}])

        self.assertIn("local LiteLLM gateway", str(ctx.exception))

    async def test_invalid_response_raises_domain_exception(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"choices": []})
            ),
        ) as client:
            gateway = GatewayChatClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
            )
            with self.assertRaises(GatewayResponseError):
                await gateway.chat_completion([{"role": "user", "content": "pergunta"}])


if __name__ == "__main__":
    unittest.main()
