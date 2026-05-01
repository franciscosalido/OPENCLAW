from __future__ import annotations

import unittest
from typing import Any

import httpx
from loguru import logger

from backend.rag.embeddings import EmbeddingError, OllamaEmbedder
from backend.rag.observability import RagObservabilityConfig


class OllamaEmbedderObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_embed_success_emits_started_and_finished_events(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            async with httpx.AsyncClient(
                base_url="http://ollama.test",
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
                ),
            ) as client:
                embedder = OllamaEmbedder(
                    client=client,
                    expected_dimensions=2,
                    observability_config=RagObservabilityConfig(enabled=True),
                )
                vector = await embedder.embed("texto sintetico confidencial")
        finally:
            logger.remove(sink_id)

        self.assertEqual(vector, [0.1, 0.2])
        self.assertEqual(
            [event["event_kind"] for event in events],
            ["embedding_call_started", "embedding_call_finished"],
        )
        self.assertEqual(events[0]["backend"], "direct_ollama")
        self.assertEqual(events[0]["alias"], "nomic-embed-text")
        self.assertEqual(events[1]["status"], "success")
        self.assertNotIn("texto sintetico confidencial", str(events))

    async def test_ollama_embed_failure_emits_failed_event(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            async with httpx.AsyncClient(
                base_url="http://ollama.test",
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json={"embeddings": [[0.1]]})
                ),
            ) as client:
                embedder = OllamaEmbedder(
                    client=client,
                    expected_dimensions=2,
                    observability_config=RagObservabilityConfig(enabled=True),
                )
                with self.assertRaises(EmbeddingError):
                    await embedder.embed("texto que nao pode aparecer")
        finally:
            logger.remove(sink_id)

        self.assertEqual(
            [event["event_kind"] for event in events],
            ["embedding_call_started", "embedding_call_failed"],
        )
        self.assertEqual(events[1]["status"], "failed")
        self.assertEqual(events[1]["error_category"], "invalid_response")
        self.assertNotIn("texto que nao pode aparecer", str(events))

    async def test_ollama_retry_behavior_remains_unchanged(self) -> None:
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
                observability_config=RagObservabilityConfig(enabled=False),
            )
            vector = await embedder.embed("chunk")

        self.assertEqual(vector, [0.5, 0.6])
        self.assertEqual(attempts, 3)
        self.assertEqual(sleeps, [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
