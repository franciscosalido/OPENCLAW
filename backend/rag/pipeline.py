"""End-to-end local RAG pipeline orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from loguru import logger

from backend.rag._validation import validate_question
from backend.rag.context_packer import RetrievedChunk
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.observability import (
    RagErrorCategory,
    RagEventKind,
    RagObservabilityConfig,
    RagObservabilityEvent,
    categorize_exception,
    emit_rag_event,
    load_rag_observability_config,
    utc_now_iso,
)
from backend.rag.run_trace import (
    RagTracingConfig,
    build_rag_run_trace,
    load_rag_tracing_config,
)


class RetrieverProtocol(Protocol):
    """Minimal retrieval interface required by the local RAG pipeline."""

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> Awaitable[list[RetrievedChunk]]:
        """Return packed chunks for a question."""
        ...


class GeneratorProtocol(Protocol):
    """Minimal generation interface required by the local RAG pipeline."""

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
        thinking_mode: bool = False,
    ) -> Awaitable[str]:
        """Generate an answer from chat messages."""
        ...


@dataclass(frozen=True)
class RagPipelineResult:
    """Final local RAG answer with citations and latency metadata."""

    question: str
    answer: str
    chunks_used: list[RetrievedChunk]
    messages: list[dict[str, str]]
    latency_ms: dict[str, float]

    @property
    def citations(self) -> list[str]:
        """Return citation ids for chunks used in the answer context."""

        return [chunk.citation_id for chunk in self.chunks_used]


@dataclass
class LocalRagPipeline:
    """Compose retrieval, prompt construction, and local generation."""

    retriever: RetrieverProtocol
    generator: GeneratorProtocol
    prompt_builder: PromptBuilder
    temperature: float | None = None
    thinking_mode: bool = False
    tracing_config: RagTracingConfig | None = None
    observability_config: RagObservabilityConfig | None = None

    def __post_init__(self) -> None:
        if self.tracing_config is None:
            self.tracing_config = load_rag_tracing_config()
        if self.observability_config is None:
            self.observability_config = load_rag_observability_config()

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> RagPipelineResult:
        """Run retrieval, build a prompt, and generate a local answer."""

        clean_question = validate_question(question)
        query_id = uuid4().hex
        total_start = time.perf_counter()
        collection_name = _infer_collection_name(
            self.retriever,
            self.tracing_config.collection_name if self.tracing_config else "unknown",
        )

        retrieval_start = time.perf_counter()
        self._emit_pipeline_event(
            RagEventKind.RETRIEVAL_STARTED,
            query_id=query_id,
            collection_name=collection_name,
            status="started",
        )
        try:
            chunks = await self.retriever.retrieve(
                clean_question,
                top_k=top_k,
                filters=filters,
            )
        except Exception as exc:
            self._emit_pipeline_event(
                RagEventKind.RETRIEVAL_FAILED,
                query_id=query_id,
                collection_name=collection_name,
                latency_ms=_elapsed_ms(retrieval_start),
                status="failed",
                error_category=categorize_exception(exc),
            )
            raise
        retrieval_ms = _elapsed_ms(retrieval_start)
        retrieval_segments = _extract_retrieval_segments(self.retriever)
        self._emit_pipeline_event(
            RagEventKind.RETRIEVAL_FINISHED,
            query_id=query_id,
            collection_name=collection_name,
            latency_ms=retrieval_ms,
            chunk_count=len(chunks),
            status="success",
        )

        prompt_start = time.perf_counter()
        messages = self.prompt_builder.build(
            clean_question,
            chunks,
            thinking_mode=self.thinking_mode,
        )
        prompt_ms = _elapsed_ms(prompt_start)

        generation_start = time.perf_counter()
        gateway_alias = _infer_gateway_alias(self.generator)
        self._emit_pipeline_event(
            RagEventKind.GENERATION_STARTED,
            query_id=query_id,
            collection_name=collection_name,
            chunk_count=len(chunks),
            gateway_alias=gateway_alias,
            status="started",
        )
        try:
            answer = await self.generator.chat(
                messages,
                temperature=self.temperature,
                thinking_mode=self.thinking_mode,
            )
        except Exception as exc:
            self._emit_pipeline_event(
                RagEventKind.GENERATION_FAILED,
                query_id=query_id,
                collection_name=collection_name,
                latency_ms=_elapsed_ms(generation_start),
                chunk_count=len(chunks),
                gateway_alias=gateway_alias,
                status="failed",
                error_category=categorize_exception(exc),
            )
            raise
        generation_ms = _elapsed_ms(generation_start)
        self._emit_pipeline_event(
            RagEventKind.GENERATION_FINISHED,
            query_id=query_id,
            collection_name=collection_name,
            latency_ms=generation_ms,
            chunk_count=len(chunks),
            gateway_alias=gateway_alias,
            status="success",
        )

        latency = {
            "retrieval_ms": retrieval_ms,
            "prompt_ms": prompt_ms,
            "generation_ms": generation_ms,
            "total_ms": _elapsed_ms(total_start),
        }
        logger.info(
            "rag_pipeline | chunks={} citations={} latency={}",
            len(chunks),
            [chunk.citation_id for chunk in chunks],
            latency,
        )
        self._emit_trace(
            retrieval_ms=retrieval_ms,
            embedding_ms=retrieval_segments.embedding_ms,
            vector_search_ms=retrieval_segments.retrieval_ms,
            context_pack_ms=retrieval_segments.context_pack_ms,
            prompt_ms=prompt_ms,
            generation_ms=generation_ms,
            total_ms=latency["total_ms"],
            chunk_count=len(chunks),
            query_id=query_id,
        )
        return RagPipelineResult(
            question=clean_question,
            answer=answer,
            chunks_used=list(chunks),
            messages=messages,
            latency_ms=latency,
        )

    def _emit_trace(
        self,
        *,
        retrieval_ms: float,
        embedding_ms: float | None = None,
        vector_search_ms: float | None = None,
        context_pack_ms: float | None = None,
        prompt_ms: float,
        generation_ms: float,
        total_ms: float,
        chunk_count: int,
        query_id: str | None = None,
        actual_embedding_dimensions: int | None = None,
    ) -> None:
        """Emit a RagRunTrace provenance record via loguru.

        When *actual_embedding_dimensions* is provided it is used as the
        observed dimension value and ``config.embedding_dimensions`` as the
        expected value.  This allows drift between the runtime embedding
        source and the configured contract to trigger
        ``EmbeddingDimensionMismatchError`` before the trace is recorded.

        When *actual_embedding_dimensions* is ``None`` both values come from
        config (current default behaviour — no mismatch possible).
        """
        config = self.tracing_config
        if config is None or not config.enabled:
            return
        collection_name = _infer_collection_name(self.retriever, config.collection_name)
        gateway_alias = _infer_gateway_alias(self.generator)
        if actual_embedding_dimensions is not None:
            observed_dims = actual_embedding_dimensions
            expected_dims = config.embedding_dimensions
        else:
            observed_dims = config.embedding_dimensions
            expected_dims = config.embedding_dimensions
        trace = build_rag_run_trace(
            collection_name=collection_name,
            embedding_backend=config.embedding_backend,
            embedding_model=config.embedding_model,
            embedding_alias=config.embedding_alias,
            embedding_dimensions=observed_dims,
            expected_dimensions=expected_dims,
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=generation_ms,
            chunk_count=chunk_count,
            query_id=query_id,
            gateway_alias=gateway_alias,
            total_latency_ms=total_ms,
            prompt_latency_ms=prompt_ms,
            context_chunk_count=chunk_count,
            routing_ms=None,
            embedding_ms=embedding_ms,
            retrieval_ms=vector_search_ms,
            context_pack_ms=context_pack_ms,
            prompt_build_ms=prompt_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
        )
        logger.bind(trace=trace.to_log_dict()).log(config.log_level, "rag_run_trace")

    def _emit_pipeline_event(
        self,
        event_kind: RagEventKind,
        *,
        query_id: str,
        collection_name: str,
        latency_ms: float | None = None,
        chunk_count: int | None = None,
        gateway_alias: str | None = None,
        status: str | None = None,
        error_category: RagErrorCategory | None = None,
    ) -> None:
        config = self.observability_config
        if config is None or not config.enabled:
            return
        if event_kind.value.startswith("retrieval_") and not config.retrieval_events_enabled:
            return
        if event_kind.value.startswith("generation_") and not config.generation_events_enabled:
            return
        tracing = self.tracing_config
        event = RagObservabilityEvent(
            event_kind=event_kind,
            timestamp_utc=utc_now_iso(),
            backend=tracing.embedding_backend if tracing else "unknown",
            alias=tracing.embedding_alias if tracing else "unknown",
            model=tracing.embedding_model if tracing else None,
            dimensions=tracing.embedding_dimensions if tracing else None,
            latency_ms=latency_ms,
            chunk_count=chunk_count,
            status=status,
            error_category=error_category,
            collection_name=collection_name,
            query_id=query_id,
            gateway_alias=gateway_alias,
        )
        emit_rag_event(event, config)


def _infer_collection_name(retriever: object, fallback: str) -> str:
    store = getattr(retriever, "store", None)
    collection_name = getattr(store, "collection_name", None)
    if isinstance(collection_name, str) and collection_name.strip():
        return collection_name.strip()
    return fallback


def _infer_gateway_alias(generator: object) -> str | None:
    model = getattr(generator, "model", None)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


@dataclass(frozen=True)
class _RetrievalSegments:
    embedding_ms: float | None
    retrieval_ms: float | None
    context_pack_ms: float | None


def _extract_retrieval_segments(retriever: object) -> _RetrievalSegments:
    timings = getattr(retriever, "last_timings", None)
    embed_ms = getattr(timings, "embed_ms", None)
    search_ms = getattr(timings, "search_ms", None)
    pack_ms = getattr(timings, "pack_ms", None)
    return _RetrievalSegments(
        embedding_ms=_optional_timing(embed_ms),
        retrieval_ms=_optional_timing(search_ms),
        context_pack_ms=_optional_timing(pack_ms),
    )


def _optional_timing(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
