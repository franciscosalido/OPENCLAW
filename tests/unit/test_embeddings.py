import json
import unittest

import httpx

from backend.rag.embeddings import OllamaEmbedder


async def no_sleep(_seconds: float) -> None:
    return None


class OllamaEmbedderTests(unittest.IsolatedAsyncioTestCase):
    async def test_embed_posts_to_ollama_embed_endpoint(self):
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            self.assertEqual(request.url.path, "/api/embed")
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(client=client, model="nomic-embed-text")
            vector = await embedder.embed(" texto sintetico ")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        self.assertEqual(
            seen_payloads,
            [{"model": "nomic-embed-text", "input": "texto sintetico"}],
        )

    async def test_embed_batch_preserves_order_and_uses_rate_limit(self):
        requested_inputs: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            text = str(payload["input"])
            requested_inputs.append(text)
            value = float(len(requested_inputs))
            return httpx.Response(200, json={"embeddings": [[value]]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(client=client, max_concurrency=1)
            vectors = await embedder.embed_batch(["um", "dois", "tres"])

        self.assertEqual(vectors, [[1.0], [2.0], [3.0]])
        self.assertEqual(requested_inputs, ["um", "dois", "tres"])

    async def test_retry_with_exponential_backoff_for_transient_status(self):
        attempts = 0
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(503, json={"error": "model loading"})
            return httpx.Response(200, json={"embeddings": [[0.5, 0.6]]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(
                client=client,
                max_retries=3,
                backoff_seconds=0.25,
                sleep=fake_sleep,
            )
            vector = await embedder.embed("chunk")

        self.assertEqual(vector, [0.5, 0.6])
        self.assertEqual(attempts, 3)
        self.assertEqual(sleeps, [0.25, 0.5])

    async def test_non_transient_http_error_is_not_retried(self):
        attempts = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(400, json={"error": "bad input"})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(client=client, max_retries=3, sleep=no_sleep)
            with self.assertRaises(httpx.HTTPStatusError):
                await embedder.embed("chunk")

        self.assertEqual(attempts, 1)

    async def test_invalid_inputs_and_config_raise_errors(self):
        with self.assertRaises(ValueError):
            OllamaEmbedder(timeout_seconds=0)
        with self.assertRaises(ValueError):
            OllamaEmbedder(max_concurrency=0)

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        ) as client:
            embedder = OllamaEmbedder(client=client)
            with self.assertRaises(ValueError):
                await embedder.embed("   ")
            with self.assertRaises(ValueError):
                await embedder.embed_batch(["valid", " "])

    async def test_invalid_ollama_response_raises_error(self):
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"embeddings": [[]]})
            ),
        ) as client:
            embedder = OllamaEmbedder(client=client)
            with self.assertRaises(ValueError):
                await embedder.embed("chunk")


if __name__ == "__main__":
    unittest.main()

