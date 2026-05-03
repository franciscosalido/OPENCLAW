from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import httpx

from backend.gateway.client import DEFAULT_LLM_BASE_URL
from backend.gateway.errors import GatewayAuthenticationError, GatewayResponseError
from backend.rag.generator import LocalGenerator


class LocalGeneratorTests(unittest.IsolatedAsyncioTestCase):
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
                await generator.chat([{"role": "user", "content": "x"}], temperature=3.0)


if __name__ == "__main__":
    unittest.main()
