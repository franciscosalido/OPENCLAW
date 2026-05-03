"""End-to-end local RAG pipeline orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from loguru import logger

from backend.gateway.routing_policy import estimate_prompt_tokens
from backend.rag._validation import validate_question
from backend.rag.context_packer import ContextBudgetResult, RetrievedChunk
from backend.rag.generation_budget import (
    GenerationBudgetConfig,
    GenerationBudgetDecision,
    decide_generation_budget,
    load_generation_budget_config,
)
from backend.rag.model_residency import (
    ModelResidencyConfig,
    ModelResidencyDecision,
    decide_model_residency,
    load_model_residency_config,
)
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
    RagRunContext,
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
        max_tokens: int | None = None,
        keep_alive: str | None = None,
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
    generation_budget_config: GenerationBudgetConfig | None = None
    model_residency_config: ModelResidencyConfig | None = None

    def __post_init__(self) -> None:
        if self.tracing_config is None:
            self.tracing_config = load_rag_tracing_config()
        if self.observability_config is None:
            self.observability_config = load_rag_observability_config()
        if self.generation_budget_config is None:
            self.generation_budget_config = load_generation_budget_config()
        if self.model_residency_config is None:
            self.model_residency_config = load_model_residency_config()

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
        run_context: RagRunContext | None = None,
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
        context_budget_result = _extract_context_budget_result(self.retriever)
        self._emit_pipeline_event(
            RagEventKind.RETRIEVAL_FINISHED,
            query_id=query_id,
            collection_name=collection_name,
            latency_ms=retrieval_ms,
            chunk_count=len(chunks),
            status="success",
        )

        gateway_alias = _infer_gateway_alias(self.generator)
        generation_budget = decide_generation_budget(
            self.generation_budget_config or GenerationBudgetConfig(),
            alias=gateway_alias,
        )
        model_residency = decide_model_residency(
            self.model_residency_config or ModelResidencyConfig(),
            alias=gateway_alias,
        )

        prompt_start = time.perf_counter()
        messages = self.prompt_builder.build(
            clean_question,
            chunks,
            thinking_mode=self.thinking_mode,
            conciseness_instruction=generation_budget.conciseness_instruction,
        )
        prompt_ms = _elapsed_ms(prompt_start)

        generation_start = time.perf_counter()
        self._emit_pipeline_event(
            RagEventKind.GENERATION_STARTED,
            query_id=query_id,
            collection_name=collection_name,
            chunk_count=len(chunks),
            gateway_alias=gateway_alias,
            status="started",
        )
        try:
            answer = await _chat_with_generation_budget(
                self.generator,
                messages=messages,
                temperature=self.temperature,
            thinking_mode=self.thinking_mode,
            generation_budget=generation_budget,
            model_residency=model_residency,
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
            context_budget_result=context_budget_result,
            generation_budget=generation_budget,
            model_residency=model_residency,
            answer_length_chars=len(answer),
            answer_token_estimate=estimate_prompt_tokens(answer),
            prompt_ms=prompt_ms,
            generation_ms=generation_ms,
            total_ms=latency["total_ms"],
            chunk_count=len(chunks),
            query_id=query_id,
            run_context=run_context,
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
        context_budget_result: ContextBudgetResult | None = None,
        generation_budget: GenerationBudgetDecision | None = None,
        model_residency: ModelResidencyDecision | None = None,
        answer_length_chars: int | None = None,
        answer_token_estimate: int | None = None,
        query_id: str | None = None,
        actual_embedding_dimensions: int | None = None,
        run_context: RagRunContext | None = None,
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
            context_budget_enabled=(
                context_budget_result.enabled
                if context_budget_result is not None
                else None
            ),
            context_budget_applied=(
                context_budget_result.applied
                if context_budget_result is not None
                else None
            ),
            context_chunks_retrieved=(
                context_budget_result.chunks_retrieved
                if context_budget_result is not None
                else None
            ),
            context_chunks_used=(
                context_budget_result.chunks_used
                if context_budget_result is not None
                else None
            ),
            context_chunks_dropped=(
                context_budget_result.chunks_dropped
                if context_budget_result is not None
                else None
            ),
            context_budget_max_chunks=(
                context_budget_result.max_context_chunks
                if context_budget_result is not None
                else None
            ),
            context_estimated_tokens_used=(
                context_budget_result.estimated_tokens_used
                if context_budget_result is not None
                else None
            ),
            answer_length_chars=answer_length_chars,
            answer_token_estimate=answer_token_estimate,
            generation_budget_enabled=(
                generation_budget.enabled if generation_budget is not None else None
            ),
            generation_budget_applied=(
                generation_budget.max_tokens_applied
                if generation_budget is not None
                else None
            ),
            generation_budget_max_tokens=(
                generation_budget.max_tokens if generation_budget is not None else None
            ),
            conciseness_instruction_applied=(
                generation_budget.conciseness_instruction_applied
                if generation_budget is not None
                else None
            ),
            model_residency_enabled=(
                model_residency.enabled if model_residency is not None else None
            ),
            keep_alive_value=(
                model_residency.keep_alive if model_residency is not None else None
            ),
            keep_alive_applied=(
                model_residency.keep_alive_applied
                if model_residency is not None
                else None
            ),
            prompt_build_ms=prompt_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
            run_context=run_context,
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


async def _chat_with_generation_budget(
    generator: GeneratorProtocol,
    *,
    messages: Sequence[dict[str, str]],
    temperature: float | None,
    thinking_mode: bool,
    generation_budget: GenerationBudgetDecision,
    model_residency: ModelResidencyDecision,
) -> str:
    return await generator.chat(
        messages,
        temperature=temperature,
        thinking_mode=thinking_mode,
        max_tokens=generation_budget.max_tokens,
        keep_alive=model_residency.keep_alive,
    )


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


def _extract_context_budget_result(retriever: object) -> ContextBudgetResult | None:
    result = getattr(retriever, "last_context_budget_result", None)
    if isinstance(result, ContextBudgetResult):
        return result
    return None


def _optional_timing(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
