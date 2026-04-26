"""Unit tests for OllamaEmbedder.

All tests use httpx.MockTransport — no real Ollama instance required.
Tests validate: API contract, retry/backoff, dimension validation, error paths.
"""

from __future__ import annotations

import json
import unittest

import httpx

from backend.rag.embeddings import EmbeddingError, OllamaEmbedder


async def no_sleep(_seconds: float) -> None:
    return None


class OllamaEmbedderTests(unittest.IsolatedAsyncioTestCase):
    async def test_embed_posts_to_ollama_embed_endpoint(self) -> None:
        """embed() sends correct payload to /api/embed and returns the vector."""
        seen_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content.decode("utf-8")))
            self.assertEqual(request.url.path, "/api/embed")
            return httpx.Response(200, json={"embeddings": [[0.1] * 3]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(
                client=client,
                model="nomic-embed-text",
                expected_dimensions=3,
            )
            vector = await embedder.embed(" texto sintetico ")

        self.assertEqual(vector, [0.1] * 3)
        self.assertEqual(
            seen_payloads,
            [{"model": "nomic-embed-text", "input": "texto sintetico"}],
        )

    async def test_embed_batch_preserves_order_and_uses_concurrency_limit(self) -> None:
        """embed_batch() returns vectors in input order and respects max_concurrency."""
        requested_inputs: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            requested_inputs.append(str(payload["input"]))
            value = float(len(requested_inputs))
            return httpx.Response(200, json={"embeddings": [[value]]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(
                client=client,
                max_concurrency=1,
                expected_dimensions=1,
            )
            vectors = await embedder.embed_batch(["um", "dois", "tres"])

        self.assertEqual(vectors, [[1.0], [2.0], [3.0]])
        self.assertEqual(requested_inputs, ["um", "dois", "tres"])

    async def test_retry_with_exponential_backoff_for_transient_status(self) -> None:
        """Transient 5xx errors trigger retry with exponential backoff (1s->2s->...)."""
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
                backoff_seconds=1.0,
                sleep=fake_sleep,
                expected_dimensions=2,
            )
            vector = await embedder.embed("chunk")

        self.assertEqual(vector, [0.5, 0.6])
        self.assertEqual(attempts, 3)
        self.assertEqual(sleeps, [1.0, 2.0])  # 1s, 2s (exponential: 1*2^0, 1*2^1)

    async def test_non_transient_http_error_is_not_retried(self) -> None:
        """400 Bad Request is not retried — fails immediately."""
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

    async def test_embed_raises_on_wrong_dimensions(self) -> None:
        """EmbeddingError is raised when Ollama returns fewer dims than expected."""

        def handler(_request: httpx.Request) -> httpx.Response:
            # Ollama returns 512-dim vector but we expect 768
            return httpx.Response(200, json={"embeddings": [[0.1] * 512]})

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            embedder = OllamaEmbedder(client=client, expected_dimensions=768)
            with self.assertRaises(EmbeddingError) as ctx:
                await embedder.embed("chunk")

        self.assertIn("768", str(ctx.exception))
        self.assertIn("512", str(ctx.exception))

    async def test_invalid_inputs_and_config_raise_errors(self) -> None:
        """ValueError/TypeError on empty text and invalid config at construction."""
        with self.assertRaises(ValueError):
            OllamaEmbedder(timeout_seconds=0)
        with self.assertRaises(ValueError):
            OllamaEmbedder(max_concurrency=0)
        with self.assertRaises(ValueError):
            OllamaEmbedder(expected_dimensions=0)

        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200)
            ),
        ) as client:
            embedder = OllamaEmbedder(client=client)
            with self.assertRaises(ValueError):
                await embedder.embed("   ")
            with self.assertRaises(ValueError):
                await embedder.embed_batch(["valid", " "])

    async def test_invalid_ollama_response_raises_embedding_error(self) -> None:
        """EmbeddingError raised when Ollama returns an empty embedding list."""
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200, json={"embeddings": [[]]}
                )
            ),
        ) as client:
            embedder = OllamaEmbedder(client=client)
            with self.assertRaises(EmbeddingError):
                await embedder.embed("chunk")


if __name__ == "__main__":
    unittest.main()
