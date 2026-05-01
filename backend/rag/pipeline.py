"""End-to-end local RAG pipeline orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from backend.rag._validation import validate_question
from backend.rag.context_packer import RetrievedChunk
from backend.rag.prompt_builder import PromptBuilder
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

    def __post_init__(self) -> None:
        if self.tracing_config is None:
            self.tracing_config = load_rag_tracing_config()

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> RagPipelineResult:
        """Run retrieval, build a prompt, and generate a local answer."""

        clean_question = validate_question(question)
        total_start = time.perf_counter()

        retrieval_start = time.perf_counter()
        chunks = await self.retriever.retrieve(
            clean_question,
            top_k=top_k,
            filters=filters,
        )
        retrieval_ms = _elapsed_ms(retrieval_start)

        prompt_start = time.perf_counter()
        messages = self.prompt_builder.build(
            clean_question,
            chunks,
            thinking_mode=self.thinking_mode,
        )
        prompt_ms = _elapsed_ms(prompt_start)

        generation_start = time.perf_counter()
        answer = await self.generator.chat(
            messages,
            temperature=self.temperature,
            thinking_mode=self.thinking_mode,
        )
        generation_ms = _elapsed_ms(generation_start)

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
            prompt_ms=prompt_ms,
            generation_ms=generation_ms,
            total_ms=latency["total_ms"],
            chunk_count=len(chunks),
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
        prompt_ms: float,
        generation_ms: float,
        total_ms: float,
        chunk_count: int,
    ) -> None:
        config = self.tracing_config
        if config is None or not config.enabled:
            return
        collection_name = _infer_collection_name(self.retriever, config.collection_name)
        gateway_alias = _infer_gateway_alias(self.generator)
        trace = build_rag_run_trace(
            collection_name=collection_name,
            embedding_backend=config.embedding_backend,
            embedding_model=config.embedding_model,
            embedding_alias=config.embedding_alias,
            embedding_dimensions=config.embedding_dimensions,
            expected_dimensions=config.embedding_dimensions,
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=generation_ms,
            chunk_count=chunk_count,
            gateway_alias=gateway_alias,
            total_latency_ms=total_ms,
            prompt_latency_ms=prompt_ms,
            context_chunk_count=chunk_count,
        )
        logger.bind(trace=trace.to_log_dict()).log(config.log_level, "rag_run_trace")


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


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
