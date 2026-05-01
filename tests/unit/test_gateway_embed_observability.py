from __future__ import annotations

import unittest
from typing import Any

import httpx
from loguru import logger

from backend.gateway.client import DEFAULT_LLM_BASE_URL, GatewayRuntimeConfig
from backend.gateway.embed_client import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    GatewayEmbedClient,
)
from backend.gateway.errors import GatewayConnectionError
from backend.rag.observability import RagObservabilityConfig


def _embedding_response() -> dict[str, object]:
    return {
        "data": [
            {
                "index": 0,
                "embedding": [0.1] * DEFAULT_EMBEDDING_DIMENSIONS,
            }
        ]
    }


class GatewayEmbedObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_embed_success_emits_started_and_finished_events(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            async with httpx.AsyncClient(
                base_url=DEFAULT_LLM_BASE_URL,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json=_embedding_response())
                ),
            ) as client:
                gateway = GatewayEmbedClient(
                    config=GatewayRuntimeConfig(api_key="secret-test-key"),
                    client=client,
                    observability_config=RagObservabilityConfig(
                        enabled=True,
                        log_level="INFO",
                    ),
                )
                vector = await gateway.embed("texto sensivel sintetico")
        finally:
            logger.remove(sink_id)

        self.assertEqual(len(vector), DEFAULT_EMBEDDING_DIMENSIONS)
        self.assertEqual(
            [event["event_kind"] for event in events],
            ["embedding_call_started", "embedding_call_finished"],
        )
        self.assertEqual(events[0]["backend"], "gateway_litellm")
        self.assertEqual(events[0]["alias"], "quimera_embed")
        self.assertEqual(events[1]["status"], "success")
        self.assertEqual(events[1]["batch_size"], 1)
        joined = str(events)
        self.assertNotIn("texto sensivel sintetico", joined)
        self.assertNotIn("secret-test-key", joined)

    async def test_gateway_embed_failure_emits_failed_safe_category(self) -> None:
        events: list[dict[str, object]] = []

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("secret connection detail")

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        async def fake_sleep(_seconds: float) -> None:
            return None

        sink_id = logger.add(sink, level="INFO")
        try:
            async with httpx.AsyncClient(
                base_url=DEFAULT_LLM_BASE_URL,
                transport=httpx.MockTransport(handler),
            ) as client:
                gateway = GatewayEmbedClient(
                    config=GatewayRuntimeConfig(api_key="secret-test-key"),
                    client=client,
                    max_retries=0,
                    sleep=fake_sleep,
                    observability_config=RagObservabilityConfig(enabled=True),
                )
                with self.assertRaises(GatewayConnectionError):
                    await gateway.embed("texto que nao deve ir ao log")
        finally:
            logger.remove(sink_id)

        self.assertEqual(
            [event["event_kind"] for event in events],
            ["embedding_call_started", "embedding_call_failed"],
        )
        self.assertEqual(events[1]["status"], "failed")
        self.assertEqual(events[1]["error_category"], "connection")
        joined = str(events)
        self.assertNotIn("texto que nao deve ir ao log", joined)
        self.assertNotIn("secret-test-key", joined)
        self.assertNotIn("secret connection detail", joined)

    async def test_gateway_embed_retry_behavior_remains_unchanged(self) -> None:
        calls = 0
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503)
            return httpx.Response(200, json=_embedding_response())

        async with httpx.AsyncClient(
            base_url=DEFAULT_LLM_BASE_URL,
            transport=httpx.MockTransport(handler),
        ) as client:
            gateway = GatewayEmbedClient(
                config=GatewayRuntimeConfig(api_key="dev-key"),
                client=client,
                sleep=fake_sleep,
                observability_config=RagObservabilityConfig(enabled=False),
            )
            vector = await gateway.embed("texto sintetico")

        self.assertEqual(len(vector), DEFAULT_EMBEDDING_DIMENSIONS)
        self.assertEqual(calls, 3)
        self.assertEqual(sleeps, [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
