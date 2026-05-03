from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger

from backend.rag.context_packer import RetrievedChunk
from backend.rag.observability import RagObservabilityConfig
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.run_trace import RagTracingConfig


class FakeStore:
    collection_name = "synthetic_observability_collection"


class FakeRetriever:
    store = FakeStore()

    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                id="obs_doc:0",
                score=0.91,
                doc_id="obs_doc",
                chunk_index=0,
                text="chunk text must never appear in lifecycle events",
                token_count=8,
                rank=1,
                payload={"secret": "do-not-log"},
            )
        ]


class FakeGenerator:
    model = "local_rag"

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        del max_tokens
        return "Resposta sintetica com citacao [obs_doc#0]."


def _tracing_config(enabled: bool = True) -> RagTracingConfig:
    return RagTracingConfig(
        enabled=enabled,
        log_level="INFO",
        collection_name="configured_collection",
        embedding_backend="gateway_litellm_current",
        embedding_model="nomic-embed-text",
        embedding_alias="quimera_embed",
        embedding_dimensions=768,
    ).validated()


class RagPipelineObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_emits_retrieval_and_generation_events(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=FakeGenerator(),
                prompt_builder=PromptBuilder(),
                tracing_config=_tracing_config(),
                observability_config=RagObservabilityConfig(enabled=True),
            )
            await pipeline.ask("Pergunta sintetica segura?")
        finally:
            logger.remove(sink_id)

        kinds = [event["event_kind"] for event in events]
        self.assertEqual(
            kinds,
            [
                "retrieval_started",
                "retrieval_finished",
                "generation_started",
                "generation_finished",
            ],
        )
        self.assertTrue(all(event["query_id"] == events[0]["query_id"] for event in events))
        self.assertEqual(events[1]["chunk_count"], 1)
        self.assertEqual(events[3]["gateway_alias"], "local_rag")
        joined = str(events)
        self.assertNotIn("Pergunta sintetica segura", joined)
        self.assertNotIn("chunk text must never appear", joined)
        self.assertNotIn("do-not-log", joined)
        self.assertNotIn("Resposta sintetica", joined)

    async def test_pipeline_observability_disabled_emits_no_events(self) -> None:
        events: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            event = message.record["extra"].get("event")
            if isinstance(event, dict):
                events.append(event)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=FakeGenerator(),
                prompt_builder=PromptBuilder(),
                tracing_config=_tracing_config(enabled=False),
                observability_config=RagObservabilityConfig(enabled=False),
            )
            await pipeline.ask("Pergunta sintetica segura?")
        finally:
            logger.remove(sink_id)

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
