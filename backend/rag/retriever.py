"""Retriever orchestration for the local RAG pipeline."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, cast

from loguru import logger

from backend.rag.context_packer import ContextPacker, RetrievedChunk


DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.3

T = TypeVar("T")


class EmbedderProtocol(Protocol):
    """Minimal async embedding interface required by Retriever."""

    def embed(self, text: str) -> Awaitable[list[float]]:
        """Embed one query string."""
        ...


class VectorStoreProtocol(Protocol):
    """Minimal vector-store search interface required by Retriever."""

    def search(
        self,
        vector: Sequence[float],
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]:
        """Search vector neighbors and return dictionaries."""
        ...


class ContextPackerProtocol(Protocol):
    """Minimal context-packer interface required by Retriever."""

    def pack(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        """Pack retrieved chunks for prompting."""
        ...


@dataclass(frozen=True)
class RetrievalTimings:
    """Latency timings for one retrieval call, in milliseconds."""

    embed_ms: float
    search_ms: float
    pack_ms: float
    total_ms: float

    def as_dict(self) -> dict[str, float]:
        """Return a plain dictionary for logs or future CLI output."""

        return {
            "embed_ms": self.embed_ms,
            "search_ms": self.search_ms,
            "pack_ms": self.pack_ms,
            "total_ms": self.total_ms,
        }


@dataclass
class Retriever:
    """Orchestrate query embedding, vector search, and context packing."""

    embedder: EmbedderProtocol
    store: VectorStoreProtocol
    packer: ContextPackerProtocol = field(default_factory=ContextPacker)
    top_k: int = DEFAULT_TOP_K
    score_threshold: float | None = DEFAULT_SCORE_THRESHOLD
    last_timings: RetrievalTimings | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        _validate_top_k(self.top_k)
        _validate_score_threshold(self.score_threshold)

    async def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve and pack local context for one question.

        The method performs no remote calls by itself. It delegates embedding and
        vector search to injected local components, which keeps the workflow
        testable with fakes and mocks.
        """

        clean_question = _validate_question(question)
        effective_top_k = self.top_k if top_k is None else top_k
        _validate_top_k(effective_top_k)

        total_start = time.perf_counter()

        embed_start = time.perf_counter()
        query_vector = await self.embedder.embed(clean_question)
        embed_ms = _elapsed_ms(embed_start)

        search_start = time.perf_counter()
        raw_results = await _maybe_await(
            self.store.search(
                query_vector,
                top_k=effective_top_k,
                score_threshold=self.score_threshold,
                filters=filters,
            )
        )
        search_ms = _elapsed_ms(search_start)

        pack_start = time.perf_counter()
        retrieved_chunks = [
            RetrievedChunk.from_mapping(result, rank=index + 1)
            for index, result in enumerate(raw_results)
        ]
        packed_chunks = self.packer.pack(retrieved_chunks)
        pack_ms = _elapsed_ms(pack_start)

        self.last_timings = RetrievalTimings(
            embed_ms=embed_ms,
            search_ms=search_ms,
            pack_ms=pack_ms,
            total_ms=_elapsed_ms(total_start),
        )
        logger.debug(
            "retrieve | top_k={} raw={} packed={} timings={}",
            effective_top_k,
            len(raw_results),
            len(packed_chunks),
            self.last_timings.as_dict(),
        )
        return packed_chunks


async def _maybe_await(value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await cast(Awaitable[T], value)
    return value


def _validate_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question cannot be empty or whitespace")
    return clean_question


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")


def _validate_score_threshold(score_threshold: float | None) -> None:
    if score_threshold is None:
        return
    if isinstance(score_threshold, bool) or not isinstance(score_threshold, (int, float)):
        raise TypeError("score_threshold must be numeric or None")
    if not 0.0 <= float(score_threshold) <= 1.0:
        raise ValueError("score_threshold must be between 0.0 and 1.0")


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
