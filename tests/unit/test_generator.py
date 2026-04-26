from __future__ import annotations

import json
import unittest

import httpx

from backend.rag.generator import GenerationError, LocalGenerator


class LocalGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_posts_to_ollama_chat_endpoint(self) -> None:
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            self.assertEqual(request.url.path, "/api/chat")
            return httpx.Response(
                200,
                json={"message": {"content": "Resposta com [doc-a#0]."}},
            )

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            generator = LocalGenerator(
                client=client,
                model="qwen3:14b",
                max_tokens=128,
            )
            answer = await generator.chat(
                [
                    {"role": "system", "content": "sistema"},
                    {"role": "user", "content": "/no_think pergunta"},
                ]
            )

        self.assertEqual(answer, "Resposta com [doc-a#0].")
        self.assertEqual(seen_payloads[0]["model"], "qwen3:14b")
        self.assertEqual(seen_payloads[0]["stream"], False)
        self.assertEqual(seen_payloads[0]["options"], {"temperature": 0.2, "num_predict": 128})

    async def test_chat_strips_thinking_blocks_when_disabled(self) -> None:
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "message": {
                            "content": "<think>rascunho interno</think>Resposta final [doc-a#0]."
                        }
                    },
                )
            ),
        ) as client:
            generator = LocalGenerator(client=client)
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta sintetica"}],
                thinking_mode=False,
            )

        self.assertEqual(answer, "Resposta final [doc-a#0].")

    async def test_chat_keeps_thinking_blocks_when_enabled(self) -> None:
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "message": {
                            "content": "<think>rascunho</think>Resposta final [doc-a#0]."
                        }
                    },
                )
            ),
        ) as client:
            generator = LocalGenerator(client=client)
            answer = await generator.chat(
                [{"role": "user", "content": "pergunta sintetica"}],
                thinking_mode=True,
            )

        self.assertIn("<think>rascunho</think>", answer)

    async def test_invalid_response_raises_generation_error(self) -> None:
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"message": {}})
            ),
        ) as client:
            generator = LocalGenerator(client=client)
            with self.assertRaises(GenerationError):
                await generator.chat([{"role": "user", "content": "pergunta"}])

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
            base_url="http://ollama.test",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        ) as client:
            generator = LocalGenerator(client=client)
            with self.assertRaises(ValueError):
                await generator.chat([])
            with self.assertRaises(ValueError):
                await generator.chat([{"role": "tool", "content": "x"}])
            with self.assertRaises(ValueError):
                await generator.chat([{"role": "user", "content": "x"}], temperature=3.0)


if __name__ == "__main__":
    unittest.main()
