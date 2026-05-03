from __future__ import annotations

import dataclasses
import unittest
from collections.abc import Mapping, Sequence
from typing import Any, cast

from loguru import logger

from backend.rag.collection_guard import EmbeddingDimensionMismatchError
from backend.rag.context_packer import ContextBudgetResult, RetrievedChunk
from backend.rag.generation_budget import GenerationBudgetConfig
from backend.rag.model_residency import ModelResidencyConfig
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.run_trace import (
    RagRunTrace,
    RagTracingConfig,
    build_rag_run_trace,
    extract_ollama_metrics,
    load_rag_tracing_config,
)
from backend.rag.retriever import RetrievalTimings


FORBIDDEN_KEYS = {
    "query",
    "question",
    "prompt",
    "raw_user_input",
    "answer",
    "chunks",
    "chunk_text",
    "vectors",
    "embeddings",
    "payload",
    "qdrant_payload",
    "api_key",
    "authorization",
    "headers",
    "secret",
    "password",
    "raw_response",
    "raw_exception",
    "exception_message",
    "traceback",
    "model_weights_path",
}


class FakeStore:
    collection_name = "synthetic_trace_collection"


class FakeRetriever:
    store = FakeStore()
    last_timings: RetrievalTimings | None = None
    last_context_budget_result: ContextBudgetResult | None = None

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


class TimedFakeRetriever(FakeRetriever):
    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        chunks = await super().retrieve(question, top_k=top_k, filters=filters)
        self.last_timings = RetrievalTimings(
            embed_ms=1.25,
            search_ms=2.5,
            pack_ms=0.75,
            total_ms=4.8,
        )
        return chunks


class BudgetedFakeRetriever(FakeRetriever):
    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        del question, top_k, filters
        self.last_context_budget_result = ContextBudgetResult(
            enabled=True,
            applied=True,
            chunks_retrieved=5,
            chunks_used=3,
            chunks_dropped=2,
            max_context_chunks=3,
            estimated_tokens_used=24,
        )
        return [
            RetrievedChunk(
                id=f"trace_doc:{index}",
                score=0.9 - index / 10,
                doc_id="trace_doc",
                chunk_index=index,
                text=f"synthetic budgeted chunk {index}",
                token_count=8,
                rank=index + 1,
                payload={"source": "synthetic", "secret": "do-not-log"},
            )
            for index in range(3)
        ]


class FakeGenerator:
    model = "local_rag"

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
        max_tokens: int | None = None,
        keep_alive: str | None = None,
    ) -> str:
        del messages, temperature, thinking_mode, max_tokens, keep_alive
        return "Resposta sintetica segura com citacao [trace_doc#0]."


class CapturingGenerator:
    model: str
    max_tokens_seen: int | None
    keep_alive_seen: str | None

    def __init__(self, model: str) -> None:
        self.model = model
        self.max_tokens_seen = None
        self.keep_alive_seen = None

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
        max_tokens: int | None = None,
        keep_alive: str | None = None,
    ) -> str:
        del messages, temperature, thinking_mode
        self.max_tokens_seen = max_tokens
        self.keep_alive_seen = keep_alive
        return "Resposta sintetica com citacao [trace_doc#0]."


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

    def test_segment_fields_are_optional(self) -> None:
        trace = _trace()
        data = trace.to_log_dict()

        self.assertIsNone(trace.routing_ms)
        self.assertIsNone(trace.embedding_ms)
        self.assertIsNone(trace.retrieval_ms)
        self.assertIsNone(trace.context_pack_ms)
        self.assertIsNone(trace.prompt_build_ms)
        self.assertIsNone(trace.generation_ms)
        self.assertIsNone(trace.total_ms)
        self.assertIsNone(trace.run_context)
        self.assertIsNone(trace.context_budget_enabled)
        self.assertIsNone(trace.context_budget_applied)
        self.assertIsNone(trace.context_chunks_used)
        self.assertIsNone(trace.context_chunks_dropped)
        self.assertIsNone(trace.answer_length_chars)
        self.assertIsNone(trace.answer_token_estimate)
        self.assertIsNone(trace.generation_budget_enabled)
        self.assertIsNone(trace.generation_budget_applied)
        self.assertIsNone(trace.generation_budget_max_tokens)
        self.assertIsNone(trace.conciseness_instruction_applied)
        self.assertIsNone(trace.model_residency_enabled)
        self.assertIsNone(trace.keep_alive_value)
        self.assertIsNone(trace.keep_alive_applied)
        self.assertFalse(trace.ollama_metrics_available)
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in data}))

    def test_to_log_dict_includes_segment_fields_when_present(self) -> None:
        trace = _trace(
            routing_ms=0.1,
            embedding_ms=1.2,
            retrieval_ms=2.3,
            context_pack_ms=0.4,
            context_budget_enabled=True,
            context_budget_applied=True,
            context_chunks_retrieved=5,
            context_chunks_used=3,
            context_chunks_dropped=2,
            context_budget_max_chunks=3,
            context_estimated_tokens_used=120,
            answer_length_chars=48,
            answer_token_estimate=12,
            generation_budget_enabled=True,
            generation_budget_applied=True,
            generation_budget_max_tokens=768,
            conciseness_instruction_applied=True,
            model_residency_enabled=True,
            keep_alive_value="5m",
            keep_alive_applied=True,
            prompt_build_ms=0.5,
            generation_ms=31.0,
            total_ms=35.0,
            run_context="warm_model",
        )

        data = trace.to_log_dict()

        self.assertEqual(data["routing_ms"], 0.1)
        self.assertEqual(data["embedding_ms"], 1.2)
        self.assertEqual(data["retrieval_ms"], 2.3)
        self.assertEqual(data["context_pack_ms"], 0.4)
        self.assertEqual(data["context_budget_enabled"], True)
        self.assertEqual(data["context_budget_applied"], True)
        self.assertEqual(data["context_chunks_retrieved"], 5)
        self.assertEqual(data["context_chunks_used"], 3)
        self.assertEqual(data["context_chunks_dropped"], 2)
        self.assertEqual(data["context_budget_max_chunks"], 3)
        self.assertEqual(data["context_estimated_tokens_used"], 120)
        self.assertEqual(data["answer_length_chars"], 48)
        self.assertEqual(data["answer_token_estimate"], 12)
        self.assertEqual(data["generation_budget_enabled"], True)
        self.assertEqual(data["generation_budget_applied"], True)
        self.assertEqual(data["generation_budget_max_tokens"], 768)
        self.assertEqual(data["conciseness_instruction_applied"], True)
        self.assertEqual(data["model_residency_enabled"], True)
        self.assertEqual(data["keep_alive_value"], "5m")
        self.assertEqual(data["keep_alive_applied"], True)
        self.assertEqual(data["prompt_build_ms"], 0.5)
        self.assertEqual(data["generation_ms"], 31.0)
        self.assertEqual(data["total_ms"], 35.0)
        self.assertEqual(data["run_context"], "warm_model")
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in data}))

    def test_legacy_latency_fields_mirror_segment_fields_for_compatibility(self) -> None:
        # Intentional backward compatibility, not accidental duplication:
        # new consumers should prefer prompt_build_ms/generation_ms/total_ms.
        trace = _trace(
            prompt_latency_ms=0.5,
            generation_latency_ms=31.0,
            total_latency_ms=35.0,
            prompt_build_ms=0.5,
            generation_ms=31.0,
            total_ms=35.0,
        )

        data = trace.to_log_dict()

        self.assertEqual(data["prompt_latency_ms"], data["prompt_build_ms"])
        self.assertEqual(data["generation_latency_ms"], data["generation_ms"])
        self.assertEqual(data["total_latency_ms"], data["total_ms"])

    def test_invalid_generation_budget_max_tokens_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trace(generation_budget_max_tokens=0)

    def test_empty_keep_alive_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trace(keep_alive_value=" ")

    def test_total_ms_is_direct_field_not_sum_assumption(self) -> None:
        trace = _trace(
            routing_ms=1.0,
            embedding_ms=2.0,
            retrieval_ms=3.0,
            context_pack_ms=4.0,
            prompt_build_ms=5.0,
            generation_ms=6.0,
            total_ms=99.0,
        )

        data = trace.to_log_dict()

        self.assertEqual(data["total_ms"], 99.0)
        self.assertNotEqual(
            data["total_ms"],
            sum(
                cast(
                    float,
                    data[key],
                )
                for key in (
                    "routing_ms",
                    "embedding_ms",
                    "retrieval_ms",
                    "context_pack_ms",
                    "prompt_build_ms",
                    "generation_ms",
                )
            ),
        )

    def test_ollama_metrics_none_when_unavailable(self) -> None:
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

        data = trace.to_log_dict()

        self.assertFalse(data["ollama_metrics_available"])
        self.assertNotIn("ollama_total_duration_ms", data)
        self.assertIsNone(trace.ollama_eval_duration_ms)

    def test_ollama_metrics_convert_ns_to_ms_if_available(self) -> None:
        metadata = {
            "total_duration": 3_000_000,
            "load_duration": 4_000_000,
            "prompt_eval_count": 12,
            "prompt_eval_duration": 5_000_000,
            "eval_count": 34,
            "eval_duration": 6_000_000,
            "prompt": "must not be copied",
        }
        metrics = extract_ollama_metrics(metadata)
        self.assertTrue(metrics["ollama_metrics_available"])
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
            ollama_metrics=metadata,
        )
        data = trace.to_log_dict()

        self.assertTrue(data["ollama_metrics_available"])
        self.assertEqual(data["ollama_total_duration_ms"], 3.0)
        self.assertEqual(data["ollama_load_duration_ms"], 4.0)
        self.assertEqual(data["ollama_prompt_eval_count"], 12)
        self.assertEqual(data["ollama_prompt_eval_duration_ms"], 5.0)
        self.assertEqual(data["ollama_eval_count"], 34)
        self.assertEqual(data["ollama_eval_duration_ms"], 6.0)
        self.assertNotIn("must not be copied", str(data))

    def test_degraded_run_context_is_serialized_safely(self) -> None:
        trace = _trace(run_context="degraded_qdrant")

        self.assertEqual(trace.to_log_dict()["run_context"], "degraded_qdrant")

    def test_invalid_run_context_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trace(run_context="free-form context")

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

    async def test_pipeline_trace_contains_generation_and_prompt_build_timings(self) -> None:
        traces: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            trace = message.record["extra"].get("trace")
            if isinstance(trace, dict):
                traces.append(trace)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=TimedFakeRetriever(),
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
        # routing_ms is None at the pipeline level — pipeline does not perform
        # route selection, so the field is absent from to_log_dict() output.
        self.assertNotIn("routing_ms", trace)
        for key in (
            "embedding_ms",
            "retrieval_ms",
            "context_pack_ms",
            "prompt_build_ms",
            "generation_ms",
            "total_ms",
        ):
            self.assertIsInstance(trace[key], int | float)
            self.assertGreaterEqual(cast(float, trace[key]), 0.0)
        self.assertEqual(trace["embedding_ms"], 1.25)
        self.assertEqual(trace["retrieval_ms"], 2.5)
        self.assertEqual(trace["context_pack_ms"], 0.75)
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in trace}))

    async def test_pipeline_trace_contains_context_budget_metadata(self) -> None:
        traces: list[dict[str, object]] = []

        def sink(message: Any) -> None:
            trace = message.record["extra"].get("trace")
            if isinstance(trace, dict):
                traces.append(trace)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=BudgetedFakeRetriever(),
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
            result = await pipeline.ask("Pergunta sintetica?")
        finally:
            logger.remove(sink_id)

        self.assertEqual(len(result.chunks_used), 3)
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["context_budget_enabled"], True)
        self.assertEqual(trace["context_budget_applied"], True)
        self.assertEqual(trace["context_chunks_retrieved"], 5)
        self.assertEqual(trace["context_chunks_used"], 3)
        self.assertEqual(trace["context_chunks_dropped"], 2)
        self.assertEqual(trace["context_budget_max_chunks"], 3)
        self.assertEqual(trace["context_estimated_tokens_used"], 24)
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in trace}))

    async def test_local_rag_generation_budget_forwards_max_tokens_and_trace_metadata(self) -> None:
        traces: list[dict[str, object]] = []
        generator = CapturingGenerator("local_rag")

        def sink(message: Any) -> None:
            trace = message.record["extra"].get("trace")
            if isinstance(trace, dict):
                traces.append(trace)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=generator,
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
                generation_budget_config=GenerationBudgetConfig(
                    enabled=True,
                    max_tokens=768,
                    enforce_conciseness=True,
                ),
            )
            result = await pipeline.ask("Pergunta sintetica?")
        finally:
            logger.remove(sink_id)

        self.assertEqual(generator.max_tokens_seen, 768)
        self.assertIn("Responda de forma concisa", result.messages[1]["content"])
        self.assertIn("inclua citacoes", result.messages[1]["content"])
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["generation_budget_enabled"], True)
        self.assertEqual(trace["generation_budget_applied"], True)
        self.assertEqual(trace["generation_budget_max_tokens"], 768)
        self.assertEqual(trace["conciseness_instruction_applied"], True)
        self.assertEqual(trace["answer_length_chars"], len(result.answer))
        self.assertIsInstance(trace["answer_token_estimate"], int)
        self.assertNotIn(result.answer, str(trace))
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in trace}))

    async def test_generation_budget_disabled_does_not_forward_max_tokens(self) -> None:
        generator = CapturingGenerator("local_rag")
        pipeline = LocalRagPipeline(
            retriever=FakeRetriever(),
            generator=generator,
            prompt_builder=PromptBuilder(),
            tracing_config=RagTracingConfig(enabled=False).validated(),
            generation_budget_config=GenerationBudgetConfig(enabled=False),
        )

        result = await pipeline.ask("Pergunta sintetica?")

        self.assertIsNone(generator.max_tokens_seen)
        self.assertNotIn("Responda de forma concisa", result.messages[1]["content"])

    async def test_generation_budget_does_not_apply_to_non_rag_alias(self) -> None:
        generator = CapturingGenerator("local_chat")
        pipeline = LocalRagPipeline(
            retriever=FakeRetriever(),
            generator=generator,
            prompt_builder=PromptBuilder(),
            tracing_config=RagTracingConfig(enabled=False).validated(),
            generation_budget_config=GenerationBudgetConfig(
                enabled=True,
                max_tokens=768,
                enforce_conciseness=True,
            ),
        )

        result = await pipeline.ask("Pergunta sintetica?")

        self.assertIsNone(generator.max_tokens_seen)
        self.assertNotIn("Responda de forma concisa", result.messages[1]["content"])

    async def test_local_rag_model_residency_forwards_keep_alive_and_trace_metadata(
        self,
    ) -> None:
        traces: list[dict[str, object]] = []
        generator = CapturingGenerator("local_rag")

        def sink(message: Any) -> None:
            trace = message.record["extra"].get("trace")
            if isinstance(trace, dict):
                traces.append(trace)

        sink_id = logger.add(sink, level="INFO")
        try:
            pipeline = LocalRagPipeline(
                retriever=FakeRetriever(),
                generator=generator,
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
                model_residency_config=ModelResidencyConfig(
                    enabled=True,
                    keep_alive="5m",
                ),
            )
            await pipeline.ask("Pergunta sintetica?")
        finally:
            logger.remove(sink_id)

        self.assertEqual(generator.keep_alive_seen, "5m")
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["model_residency_enabled"], True)
        self.assertEqual(trace["keep_alive_value"], "5m")
        self.assertEqual(trace["keep_alive_applied"], True)
        self.assertTrue(FORBIDDEN_KEYS.isdisjoint({key.lower() for key in trace}))

    async def test_model_residency_does_not_apply_to_non_rag_alias(self) -> None:
        generator = CapturingGenerator("local_chat")
        pipeline = LocalRagPipeline(
            retriever=FakeRetriever(),
            generator=generator,
            prompt_builder=PromptBuilder(),
            tracing_config=RagTracingConfig(enabled=False).validated(),
            model_residency_config=ModelResidencyConfig(
                enabled=True,
                keep_alive="5m",
            ),
        )

        await pipeline.ask("Pergunta sintetica?")

        self.assertIsNone(generator.keep_alive_seen)

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
