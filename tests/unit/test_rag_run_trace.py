from __future__ import annotations

import dataclasses
import unittest
from collections.abc import Mapping, Sequence
from typing import Any, cast

from loguru import logger

from backend.rag.collection_guard import EmbeddingDimensionMismatchError
from backend.rag.context_packer import RetrievedChunk
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.run_trace import (
    RagRunTrace,
    RagTracingConfig,
    build_rag_run_trace,
    load_rag_tracing_config,
)


FORBIDDEN_KEYS = {
    "query",
    "question",
    "prompt",
    "answer",
    "chunks",
    "vectors",
    "payload",
    "api_key",
    "authorization",
    "secret",
}


class FakeStore:
    collection_name = "synthetic_trace_collection"


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
                id="trace_doc:0",
                score=0.9,
                doc_id="trace_doc",
                chunk_index=0,
                text="synthetic chunk text must not be logged in trace",
                token_count=8,
                rank=1,
                payload={"source": "synthetic", "secret": "do-not-log"},
            )
        ]


class FakeGenerator:
    model = "local_rag"

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
    ) -> str:
        return "Resposta sintetica segura com citacao [trace_doc#0]."


def _trace(**overrides: Any) -> RagRunTrace:
    values = {
        "query_id": "trace-id",
        "timestamp_utc": "2026-05-01T00:00:00Z",
        "collection_name": "collection",
        "embedding_backend": "gateway_litellm_current",
        "embedding_model": "nomic-embed-text",
        "embedding_alias": "quimera_embed",
        "embedding_dimensions": 768,
        "retrieval_latency_ms": 1.0,
        "generation_latency_ms": 2.0,
        "chunk_count": 1,
    }
    values.update(overrides)
    return RagRunTrace(**cast(Any, values))


def _pipeline_with_dims(embedding_dimensions: int = 768) -> LocalRagPipeline:
    """Return a pipeline with tracing enabled and the given configured dimensions."""
    return LocalRagPipeline(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        prompt_builder=PromptBuilder(),
        tracing_config=RagTracingConfig(
            enabled=True,
            log_level="INFO",
            collection_name="collection",
            embedding_backend="gateway_litellm_current",
            embedding_model="nomic-embed-text",
            embedding_alias="quimera_embed",
            embedding_dimensions=embedding_dimensions,
        ).validated(),
    )


class RagRunTraceTests(unittest.IsolatedAsyncioTestCase):
    def test_constructs_valid_frozen_trace(self) -> None:
        trace = _trace()

        self.assertEqual(trace.collection_name, "collection")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            trace.collection_name = "other"  # type: ignore[misc]

    def test_to_log_dict_includes_required_safe_fields(self) -> None:
        trace = _trace(gateway_alias="local_rag", total_latency_ms=3.0)

        data = trace.to_log_dict()

        self.assertEqual(data["query_id"], "trace-id")
        self.assertEqual(data["collection_name"], "collection")
        self.assertEqual(data["embedding_backend"], "gateway_litellm_current")
        self.assertEqual(data["embedding_model"], "nomic-embed-text")
        self.assertEqual(data["embedding_alias"], "quimera_embed")
        self.assertEqual(data["embedding_dimensions"], 768)
        self.assertEqual(data["gateway_alias"], "local_rag")
        self.assertEqual(data["total_latency_ms"], 3.0)

    def test_to_log_dict_excludes_forbidden_content_keys(self) -> None:
        data = _trace().to_log_dict()

        lowered_keys = {key.lower() for key in data}

        self.assertTrue(FORBIDDEN_KEYS.isdisjoint(lowered_keys))

    def test_build_helper_generates_query_id_when_absent(self) -> None:
        trace = build_rag_run_trace(
            collection_name="collection",
            embedding_backend="gateway_litellm_current",
            embedding_model="nomic-embed-text",
            embedding_alias="quimera_embed",
            embedding_dimensions=768,
            expected_dimensions=768,
            retrieval_latency_ms=1.0,
            generation_latency_ms=2.0,
            chunk_count=1,
        )

        self.assertGreater(len(trace.query_id), 20)

    def test_timestamp_utc_is_iso_like_utc_string(self) -> None:
        trace = build_rag_run_trace(
            collection_name="collection",
            embedding_backend="gateway_litellm_current",
            embedding_model="nomic-embed-text",
            embedding_alias="quimera_embed",
            embedding_dimensions=768,
            expected_dimensions=768,
            retrieval_latency_ms=1.0,
            generation_latency_ms=2.0,
            chunk_count=1,
        )

        self.assertRegex(trace.timestamp_utc, r"^\d{4}-\d{2}-\d{2}T.*Z$")

    def test_dimension_mismatch_raises_collection_guard_error(self) -> None:
        with self.assertRaises(EmbeddingDimensionMismatchError):
            build_rag_run_trace(
                collection_name="collection",
                embedding_backend="gateway_litellm_current",
                embedding_model="nomic-embed-text",
                embedding_alias="quimera_embed",
                embedding_dimensions=1536,
                expected_dimensions=768,
                retrieval_latency_ms=1.0,
                generation_latency_ms=2.0,
                chunk_count=1,
            )

    def test_negative_latency_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trace(retrieval_latency_ms=-0.1)

    def test_negative_chunk_count_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trace(chunk_count=-1)

    def test_guard_result_is_summarized_safely(self) -> None:
        trace = _trace(
            guard_result={
                "sampled_count": 3,
                "metadata_absent_count": 1,
                "backend_matches": False,
                "model_matches": True,
                "payload": {"text": "do not log"},
                "found_backends": ["direct_ollama_current"],
            }
        )

        guard_summary = trace.to_log_dict()["guard_result"]

        self.assertIsInstance(guard_summary, dict)
        assert isinstance(guard_summary, dict)
        self.assertEqual(guard_summary["sampled_count"], 3)
        self.assertEqual(guard_summary["backend_matches"], False)
        self.assertNotIn("payload", guard_summary)
        self.assertNotIn("found_backends", guard_summary)

    async def test_tracing_disabled_produces_no_trace_log(self) -> None:
        records: list[dict[str, object] | None] = []

        def sink(message: Any) -> None:
            records.append(message.record["extra"].get("trace"))

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=FakeGenerator(),
                prompt_builder=PromptBuilder(),
                tracing_config=RagTracingConfig(enabled=False).validated(),
            )
            await pipeline.ask("Pergunta sintetica?")
        finally:
            logger.remove(sink_id)

        self.assertNotIn("trace", [record for record in records if record is not None])
        self.assertEqual([record for record in records if record is not None], [])

    async def test_tracing_enabled_emits_loguru_event_with_trace_dict(self) -> None:
        traces: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            trace = message.record["extra"].get("trace")
            if isinstance(trace, dict):
                traces.append(trace)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=FakeGenerator(),
                prompt_builder=PromptBuilder(),
                tracing_config=RagTracingConfig(
                    enabled=True,
                    log_level="INFO",
                    collection_name="configured_collection",
                    embedding_backend="gateway_litellm_current",
                    embedding_model="nomic-embed-text",
                    embedding_alias="quimera_embed",
                    embedding_dimensions=768,
                ).validated(),
            )
            await pipeline.ask("Pergunta sintetica?")
        finally:
            logger.remove(sink_id)

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["collection_name"], "synthetic_trace_collection")
        self.assertEqual(trace["gateway_alias"], "local_rag")
        self.assertEqual(trace["embedding_dimensions"], 768)
        self.assertEqual(trace["chunk_count"], 1)
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in trace}))
        self.assertNotIn("synthetic chunk text", str(trace))
        self.assertNotIn("do-not-log", str(trace))

    def test_load_rag_tracing_config_reads_yaml_defaults(self) -> None:
        config = load_rag_tracing_config()

        self.assertTrue(config.enabled)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.embedding_alias, "quimera_embed")
        self.assertEqual(config.embedding_dimensions, 768)

    def test_invalid_log_level_raises(self) -> None:
        with self.assertRaises(ValueError):
            RagTracingConfig(log_level="TRACE").validated()

    def test_emit_trace_with_actual_dimensions_mismatch_raises(self) -> None:
        """actual_embedding_dimensions from an independent source triggers dimension guard.

        When the runtime embedding source reports 1024 dimensions but config
        expects 768, _emit_trace must raise EmbeddingDimensionMismatchError
        before any log event is emitted.
        """
        pipeline = _pipeline_with_dims(768)

        with self.assertRaises(EmbeddingDimensionMismatchError):
            pipeline._emit_trace(
                retrieval_ms=1.0,
                prompt_ms=0.5,
                generation_ms=2.0,
                total_ms=3.5,
                chunk_count=1,
                actual_embedding_dimensions=1024,
            )

    def test_emit_trace_without_actual_dimensions_uses_config_path(self) -> None:
        """actual_embedding_dimensions=None preserves the config-only path without error."""
        pipeline = _pipeline_with_dims(768)

        # Must not raise: both observed and expected dimensions come from config (768 == 768).
        pipeline._emit_trace(
            retrieval_ms=1.0,
            prompt_ms=0.5,
            generation_ms=2.0,
            total_ms=3.5,
            chunk_count=1,
            actual_embedding_dimensions=None,
        )


if __name__ == "__main__":
    unittest.main()
