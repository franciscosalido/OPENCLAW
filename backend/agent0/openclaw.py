"""Public OpenClaw Agent-0 ask API."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from backend.agent0.domain_routing import (
    ConfidenceScorer,
    FakeConfidenceScorer,
    RouteDecision,
    SystemState,
    load_domain_routing_config,
    route,
)
from backend.agent0.golden_questions import Citation
from backend.rag.context_packer import RetrievedChunk
from backend.rag.generator import LocalGenerator
from backend.rag.pipeline import LocalRagPipeline
from backend.rag.prompt_builder import PromptBuilder
from backend.rag.qdrant_store import QdrantVectorStore
from backend.rag.retriever import Retriever
from backend.rag.embedder_factory import create_rag_embedder


ANSWER_FORBIDDEN_KEYS = frozenset(
    {
        "prompt",
        "chunks",
        "chunk",
        "chunk_text",
        "vectors",
        "vector",
        "embeddings",
        "embedding",
        "payload",
        "headers",
        "api_key",
        "authorization",
        "secret",
        "raw_exception",
        "traceback",
    }
)


class AskBackend(Protocol):
    """Callable used to execute the routed local answer path."""

    def __call__(self, question: str, decision: RouteDecision) -> "Answer":
        """Return an answer for one already-routed question."""
        ...


@dataclass(frozen=True)
class Answer:
    """Stable public OpenClaw answer contract."""

    answer: str
    citations: tuple[Citation, ...]
    route: str
    corpus: str
    latency_ms: float
    citation_present: bool
    fallback_reason: str | None
    error_category: str | None

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")

    def to_dict(self) -> dict[str, object]:
        """Return a safe allowlisted dictionary for CLI JSON output."""

        data: dict[str, object] = {
            "answer": self.answer,
            "citations": [_citation_to_dict(citation) for citation in self.citations],
            "route": self.route,
            "corpus": self.corpus,
            "latency_ms": round(self.latency_ms, 3),
            "citation_present": self.citation_present,
        }
        if self.fallback_reason is not None:
            data["fallback_reason"] = self.fallback_reason
        if self.error_category is not None:
            data["error_category"] = self.error_category
        assert_answer_sanitized(data)
        return data


class OpenClaw:
    """Minimal stable public interface for Agent-0."""

    def __init__(
        self,
        *,
        state: SystemState | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
        ask_backend: AskBackend | None = None,
    ) -> None:
        self._state = state or SystemState(qdrant_available=True)
        self._config = load_domain_routing_config()
        self._confidence_scorer = confidence_scorer or FakeConfidenceScorer(
            default_score=self._config.retrieval_score_min
        )
        self._ask_backend = ask_backend or _default_ask_backend

    def ask(self, question: str) -> Answer:
        """Answer one question through deterministic Agent-0 local routing."""

        clean_question = _validate_question(question)
        started_at = time.perf_counter()
        try:
            decision = route(
                clean_question,
                self._state,
                self._config,
                self._confidence_scorer,
            )
            if decision.route != "local_rag":
                return Answer(
                    answer="Não há contexto local suficiente para responder com segurança.",
                    citations=(),
                    route=decision.route,
                    corpus=decision.corpus,
                    latency_ms=_elapsed_ms(started_at),
                    citation_present=False,
                    fallback_reason=decision.fallback_reason,
                    error_category=None,
                )
            result = self._ask_backend(clean_question, decision)
            return Answer(
                answer=result.answer,
                citations=result.citations,
                route=decision.route,
                corpus=decision.corpus,
                latency_ms=_elapsed_ms(started_at),
                citation_present=bool(result.citations),
                fallback_reason=result.fallback_reason,
                error_category=result.error_category,
            )
        except Exception as exc:
            return Answer(
                answer="Local Agent-0 execution failed.",
                citations=(),
                route="local_chat",
                corpus="none",
                latency_ms=_elapsed_ms(started_at),
                citation_present=False,
                fallback_reason="local_execution_failed",
                error_category=_safe_error_category(exc),
            )


def assert_answer_sanitized(value: object) -> None:
    """Reject forbidden content-bearing keys in Answer output structures."""

    hits = _forbidden_key_hits(value)
    if hits:
        raise ValueError(f"answer output contains forbidden keys: {hits}")


def _default_ask_backend(question: str, decision: RouteDecision) -> Answer:
    return asyncio.run(_run_local_rag(question, decision))


async def _run_local_rag(question: str, decision: RouteDecision) -> Answer:
    store = QdrantVectorStore(collection_name=decision.collection_name)
    embedder = create_rag_embedder()
    generator = LocalGenerator(model="local_rag")
    try:
        retriever = Retriever(embedder=embedder, store=store)
        pipeline = LocalRagPipeline(
            retriever=retriever,
            generator=generator,
            prompt_builder=PromptBuilder(),
        )
        result = await pipeline.ask(question)
        citations = tuple(
            _citation_from_chunk(
                chunk,
                question_id="ad_hoc",
                corpus=decision.corpus,
                collection_name=decision.collection_name,
            )
            for chunk in result.chunks_used
        )
        return Answer(
            answer=result.answer,
            citations=citations,
            route=decision.route,
            corpus=decision.corpus,
            latency_ms=float(result.latency_ms.get("total_ms", 0.0)),
            citation_present=bool(citations),
            fallback_reason=None,
            error_category=None,
        )
    finally:
        await _close_async_resource(embedder)
        await generator.aclose()
        store.close()


def _citation_from_chunk(
    chunk: RetrievedChunk,
    *,
    question_id: str,
    corpus: str,
    collection_name: str,
) -> Citation:
    payload = dict(chunk.payload)
    source_id = str(payload.get("source_id") or chunk.doc_id)
    origin_path = str(payload.get("origin_path") or "unknown")
    return Citation(
        question_id=question_id,
        source_id=source_id,
        doc_id=chunk.doc_id,
        chunk_id=chunk.citation_id,
        corpus=corpus,  # type: ignore[arg-type]
        collection_name=collection_name,  # type: ignore[arg-type]
        origin_path=origin_path,
        score=chunk.score,
        rank=chunk.rank or 1,
        retrieval_mode="qdrant",
        chunk_index=chunk.chunk_index,
    )


async def _close_async_resource(resource: object) -> None:
    close = getattr(resource, "aclose", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


def _citation_to_dict(citation: Citation) -> dict[str, object]:
    return {
        "question_id": citation.question_id,
        "source_id": citation.source_id,
        "doc_id": citation.doc_id,
        "chunk_id": citation.chunk_id,
        "corpus": citation.corpus,
        "collection_name": citation.collection_name,
        "origin_path": citation.origin_path,
        "score": citation.score,
        "rank": citation.rank,
        "retrieval_mode": citation.retrieval_mode,
        "chunk_index": citation.chunk_index,
    }


def _validate_question(question: str) -> str:
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question cannot be empty")
    return clean_question


def _safe_error_category(exc: Exception) -> str:
    return exc.__class__.__name__.lower()


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _forbidden_key_hits(value: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text in ANSWER_FORBIDDEN_KEYS:
                hits.append(next_path)
            hits.extend(_forbidden_key_hits(nested, next_path))
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            hits.extend(_forbidden_key_hits(nested, f"{path}[{index}]"))
    return hits
