from __future__ import annotations

import json
import os
import unittest
from collections.abc import Sequence
from typing import cast
from unittest.mock import patch

import httpx

from backend.gateway.client import (
    DEFAULT_LLM_BASE_URL,
    GatewayChatClient,
    GatewayRuntimeConfig,
)
from backend.gateway.errors import GatewayAuthenticationError, GatewayResponseError
from backend.rag.generator import LocalGenerator


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def chat_completion(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        keep_alive: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "keep_alive": keep_alive,
            }
        )
        return "Resposta fake."

    async def aclose(self) -> None:
        self.closed = True


class LocalGeneratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._env_patch = patch.dict(
            os.environ,
            {
                "QUIMERA_LLM_BASE_URL": DEFAULT_LLM_BASE_URL,
                "QUIMERA_LLM_API_KEY": "dev-key",
                "QUIMERA_LLM_MODEL": "local_chat",
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()

    async def test_chat_posts_to_litellm_chat_completions_endpoint(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            self.assertEqual(request.url.path, "/v1/chat/completions")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resposta com [doc-a#0]."}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            generator = LocalGenerator(
                client=client,
                api_key="dev-key",
                model="local_rag",
                max_tokens=128,
            )
            answer = await generator.chat(
                [
                    {"role": "system", "content": "sistema"},
                    {"role": "user", "content": "/no_think pergunta"},
                ]
            )

        self.assertEqual(answer, "Resposta com [doc-a#0].")
        self.assertEqual(seen_payloads[0]["model"], "local_rag")
        self.assertEqual(seen_payloads[0]["temperature"], 0.2)
        self.assertEqual(seen_payloads[0]["max_tokens"], 128)

    async def test_chat_call_max_tokens_overrides_generator_default(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resposta curta."}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            generator = LocalGenerator(
                client=client,
                api_key="dev-key",
                model="local_rag",
                max_tokens=2048,
            )
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta"}],
                max_tokens=768,
            )

        self.assertEqual(answer, "Resposta curta.")
        self.assertEqual(seen_payloads[0]["max_tokens"], 768)

    async def test_chat_call_forwards_keep_alive_when_provided(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resposta curta."}}]},
            )

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            generator = LocalGenerator(
                client=client,
                api_key="dev-key",
                model="local_rag",
                max_tokens=2048,
            )
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta"}],
                keep_alive="5m",
            )

        self.assertEqual(answer, "Resposta curta.")
        self.assertEqual(seen_payloads[0]["extra_body"], {"keep_alive": "5m"})

    async def test_injected_gateway_client_does_not_require_environment(
        self,
    ) -> None:
        fake_gateway = FakeGatewayClient()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                GatewayRuntimeConfig,
                "from_env",
                side_effect=AssertionError("from_env should not be called"),
            ),
        ):
            generator = LocalGenerator(
                gateway_client=cast(GatewayChatClient, fake_gateway),
                model="local_chat",
            )
            answer = await generator.chat([{"role": "user", "content": "pergunta"}])

        self.assertEqual(answer, "Resposta fake.")
        self.assertEqual(fake_gateway.calls[0]["model"], "local_chat")

    async def test_chat_strips_thinking_blocks_when_disabled(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        "<think>rascunho interno</think>"
                                        "Resposta final [doc-a#0]."
                                    )
                                }
                            }
                        ]
                    },
                )
            ),
        ) as client:
            generator = LocalGenerator(client=client, api_key="dev-key")
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta sintetica"}],
                thinking_mode=False,
            )

        self.assertEqual(answer, "Resposta final [doc-a#0].")

    async def test_chat_keeps_thinking_blocks_when_enabled(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        "<think>rascunho</think>"
                                        "Resposta final [doc-a#0]."
                                    )
                                }
                            }
                        ]
                    },
                )
            ),
        ) as client:
            generator = LocalGenerator(client=client, api_key="dev-key")
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta sintetica"}],
                thinking_mode=True,
            )

        self.assertIn("<think>rascunho</think>", answer)

    async def test_invalid_response_raises_generation_error(self) -> None:
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"choices": []})
            ),
        ) as client:
            generator = LocalGenerator(client=client, api_key="dev-key")
            with self.assertRaises(GatewayResponseError):
                await generator.chat([{"role": "user", "content": "pergunta"}])

    async def test_missing_gateway_api_key_fails_clearly(self) -> None:
        with self.assertRaises(GatewayAuthenticationError) as ctx:
            LocalGenerator(api_key="")

        self.assertIn("QUIMERA_LLM_API_KEY", str(ctx.exception))

    async def test_defaults_can_be_controlled_by_environment(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

        env = {
            "QUIMERA_LLM_BASE_URL": DEFAULT_LLM_BASE_URL,
            "QUIMERA_LLM_API_KEY": "dev-key",
            "QUIMERA_LLM_MODEL": "local_json",
        }
        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            with patch.dict(os.environ, env, clear=False):
                generator = LocalGenerator(client=client)
                answer = await generator.chat([{"role": "user", "content": "pergunta"}])

        self.assertEqual(answer, "ok")
        self.assertEqual(seen_payloads[0]["model"], "local_json")

    async def test_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            LocalGenerator(model="")
        with self.assertRaises(ValueError):
            LocalGenerator(timeout_seconds=0)
        with self.assertRaises(ValueError):
            LocalGenerator(temperature=3.0)
        with self.assertRaises(ValueError):
            LocalGenerator(max_tokens=0)

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        ) as client:
            generator = LocalGenerator(client=client, api_key="dev-key")
            with self.assertRaises(ValueError):
                await generator.chat([])
            with self.assertRaises(ValueError):
                await generator.chat([{"role": "tool", "content": "x"}])
            with self.assertRaises(ValueError):
                await generator.chat(
                    [{"role": "user", "content": "x"}], temperature=3.0
                )


if __name__ == "__main__":
    unittest.main()
