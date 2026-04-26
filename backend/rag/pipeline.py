"""End-to-end local RAG pipeline orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from backend.rag.context_packer import RetrievedChunk
from backend.rag.prompt_builder import PromptBuilder


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

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> RagPipelineResult:
        """Run retrieval, build a prompt, and generate a local answer."""

        clean_question = _validate_question(question)
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
        return RagPipelineResult(
            question=clean_question,
            answer=answer,
            chunks_used=list(chunks),
            messages=messages,
            latency_ms=latency,
        )


def _validate_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question cannot be empty or whitespace")
    return clean_question


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
