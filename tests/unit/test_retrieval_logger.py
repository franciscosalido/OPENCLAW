"""Unit tests for safe retrieval observability logging."""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

import backend.rag.retrieval_logger as retrieval_logger_module
from backend.rag.hybrid_retriever import (
    AsyncHybridRetriever,
    HybridRetrieverConfig,
    RetrievalMode,
    SearchHit,
)
from backend.rag.retrieval_logger import (
    ENV_DEFAULT,
    FORBIDDEN_LOG_KEYS,
    MAX_TOP_K_SCORES,
    RETRIEVAL_LOG_SCHEMA_VERSION,
    FusionLogSummary,
    InMemoryRetrievalLogger,
    LoguruRetrievalLogger,
    NullRetrievalLogger,
    PythonLoggingRetrievalLogger,
    RetrievalEvent,
    ScoreStats,
    build_retrieval_event,
    compute_score_stats,
    event_to_json,
    event_to_log_dict,
    extract_scores_from_results,
    make_event_id,
    make_query_hash,
    safe_log_retrieval_event,
    safe_ms,
    sanitize_scores,
)
from backend.rag.sparse_vector import SparseVector


class BadLogger:
    def log_event(self, event: RetrievalEvent) -> None:
        raise RuntimeError("sink failed with private data")


class FakeDenseEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2]


class FakeSparseEmbedder:
    async def embed(self, text: str) -> SparseVector:
        return SparseVector(indices=[1], values=[1.0])


class FakeDenseSearcher:
    def __init__(self, hits: Sequence[SearchHit]) -> None:
        self.hits = tuple(hits)

    async def search_dense(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: list[float],
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        return self.hits


class FakeSparseSearcher:
    def __init__(self, hits: Sequence[SearchHit]) -> None:
        self.hits = tuple(hits)

    async def search_sparse(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: SparseVector,
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        return self.hits


class RrfScoreObject:
    def __init__(self, rrf_score: float) -> None:
        self.rrf_score = rrf_score


def event(**overrides: object) -> RetrievalEvent:
    values: dict[str, object] = {
        "schema_version": RETRIEVAL_LOG_SCHEMA_VERSION,
        "event_id": "event-1",
        "level": "INFO",
        "mode": "hybrid",
        "query_hash": "abcdef1234567890",
        "query_len": 12,
        "query_is_redacted": True,
        "embed_dense_ms": 1.23456,
        "embed_sparse_ms": 2.34567,
        "search_ms": 3.45678,
        "total_ms": 9.87654,
        "chunks_returned": 2,
        "top_k_scores": (0.987654321, 0.123456789),
        "score_stats": compute_score_stats((0.987654321, 0.123456789)),
        "fusion": FusionLogSummary(
            strategy="weighted_rrf",
            profile="default",
            dense_weight=1.0,
            sparse_weight=1.0,
            k=60.0,
        ),
    }
    values.update(overrides)
    return RetrievalEvent(
        schema_version=cast(str, values["schema_version"]),
        event_id=cast(str, values["event_id"]),
        level=cast(Any, values["level"]),
        mode=cast(Any, values["mode"]),
        query_hash=cast(str, values["query_hash"]),
        query_len=cast(int, values["query_len"]),
        query_is_redacted=cast(bool, values["query_is_redacted"]),
        embed_dense_ms=cast(float, values["embed_dense_ms"]),
        embed_sparse_ms=cast(float, values["embed_sparse_ms"]),
        search_ms=cast(float, values["search_ms"]),
        total_ms=cast(float, values["total_ms"]),
        chunks_returned=cast(int, values["chunks_returned"]),
        top_k_scores=cast(tuple[float, ...], values["top_k_scores"]),
        score_stats=cast(ScoreStats, values["score_stats"]),
        fusion=cast(FusionLogSummary, values["fusion"]),
        request_id=cast(str | None, values.get("request_id")),
        correlation_id=cast(str | None, values.get("correlation_id")),
        tenant_id=cast(str | None, values.get("tenant_id")),
        otelTraceID=cast(str | None, values.get("otelTraceID")),
        otelSpanID=cast(str | None, values.get("otelSpanID")),
        otelServiceName=cast(str | None, values.get("otelServiceName")),
        otelTraceSampled=cast(bool | None, values.get("otelTraceSampled")),
    )


def hit(result_id: str, doc_id: str, score: float) -> SearchHit:
    return SearchHit(result_id=result_id, score=score, payload={"doc_id": doc_id})


def make_retriever(
    *,
    mode: RetrievalMode,
    logger: InMemoryRetrievalLogger | BadLogger,
) -> AsyncHybridRetriever:
    return AsyncHybridRetriever(
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        dense_searcher=FakeDenseSearcher([hit("chunk-a", "doc-a", 0.9)]),
        sparse_searcher=FakeSparseSearcher([hit("chunk-a", "doc-a", 0.8)]),
        config=HybridRetrieverConfig(
            collection_name="quimera_knowledge_v2",
            dense_vector_name="dense",
            sparse_vector_name="sparse",
            mode=mode,
        ),
        retrieval_logger=logger,
    )


def test_retrieval_event_valid_serializes() -> None:
    built = event()
    payload = built.to_dict()

    assert payload["schema_version"] == RETRIEVAL_LOG_SCHEMA_VERSION
    assert payload["query_is_redacted"] is True
    assert "query" not in payload
    assert "query_text" not in payload
    assert event_to_log_dict(built) == payload
    assert json.loads(event_to_json(built))["event_id"] == "event-1"


def test_retrieval_event_rejects_invalid_core_fields() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        event(schema_version="other")
    with pytest.raises(ValueError, match="mode"):
        event(mode=cast(Any, "sparse_only"))
    with pytest.raises(ValueError, match="level"):
        event(level=cast(Any, "TRACE"))
    with pytest.raises(ValueError, match="event_id"):
        event(event_id="")
    with pytest.raises(ValueError, match="event_id"):
        event(event_id="a\x00b")
    with pytest.raises(ValueError, match="query_hash"):
        event(query_hash="")
    with pytest.raises(ValueError, match="query_hash"):
        event(query_hash="a\x00b")
    with pytest.raises(ValueError, match="query_len"):
        event(query_len=-1)
    with pytest.raises(ValueError, match="chunks_returned"):
        event(chunks_returned=-1)
    with pytest.raises(ValueError, match="query_is_redacted"):
        event(query_is_redacted=False)


def test_latency_validation_and_safe_ms() -> None:
    assert safe_ms(-3.3333) == 0.0
    assert safe_ms(1.23456) == 1.235

    with pytest.raises(ValueError, match="finite"):
        safe_ms(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        event(total_ms=float("inf"))
    with pytest.raises(TypeError, match="numeric"):
        safe_ms(cast(float, True))


def test_query_hash_privacy_and_event_builder() -> None:
    first = make_query_hash("  Selic e FIIs  ")
    second = make_query_hash("Selic e FIIs")
    third = make_query_hash("outra query")

    assert first == second
    assert first != third
    assert make_event_id(first, "hybrid", 123) == make_event_id(first, "hybrid", 123)

    built = build_retrieval_event(
        query="consulta privada sobre MXRF11",
        mode="hybrid",
        embed_dense_ms=1.0,
        embed_sparse_ms=2.0,
        search_ms=3.0,
        total_ms=6.0,
        top_k_scores=(0.9, 0.8),
        fusion=FusionLogSummary(strategy="weighted_rrf", profile="default", k=60.0),
        chunks_returned=2,
        started_at_ns=10,
    )
    serialized = event_to_json(built)

    assert "consulta privada" not in serialized
    assert "query" not in built.to_dict()
    assert "query_text" not in built.to_dict()

    with pytest.raises(ValueError, match="query"):
        make_query_hash("a\x00b")
    with pytest.raises(ValueError, match="query"):
        make_query_hash("   ")


def test_score_sanitization_and_stats() -> None:
    scores = tuple(float(index) / 10.0 for index in range(20))

    sanitized = sanitize_scores(scores)
    assert len(sanitized) == MAX_TOP_K_SCORES
    assert sanitize_scores((0.123456789,)) == (0.123457,)

    with pytest.raises(ValueError, match="finite"):
        sanitize_scores((float("nan"),))
    with pytest.raises(ValueError, match="finite"):
        compute_score_stats((float("inf"),))
    with pytest.raises(TypeError, match="numeric"):
        sanitize_scores(cast(Sequence[float], (True,)))
    with pytest.raises(TypeError, match="numeric"):
        sanitize_scores(cast(Sequence[float], ("bad",)))

    empty = compute_score_stats(())
    assert empty == ScoreStats(
        count=0,
        score_min=0.0,
        score_max=0.0,
        score_mean=0.0,
        score_p50=0.0,
        rank1_gap=0.0,
    )
    one = compute_score_stats((0.7,))
    assert one.score_p50 == 0.7
    assert one.rank1_gap == 0.0
    two = compute_score_stats((0.9, 0.2))
    assert two.rank1_gap == 0.7

    ascending = compute_score_stats((0.1, 0.9))
    assert ascending.rank1_gap == -0.8


def test_extract_scores_from_result_like_objects() -> None:
    scores = extract_scores_from_results(
        [
            {"score": 0.1},
            {"rrf_score": 0.2, "score": 0.0},
            RrfScoreObject(0.3),
            object(),
        ]
    )

    assert scores == (0.1, 0.2, 0.3)


def test_fusion_summary_validation_and_serialization() -> None:
    dense_only = FusionLogSummary(strategy="none")
    assert dense_only.to_dict() == {
        "strategy": "none",
        "profile": None,
        "dense_weight": None,
        "sparse_weight": None,
        "k": None,
    }

    weighted = FusionLogSummary(
        strategy="weighted_rrf",
        profile="default",
        dense_weight=1.0,
        sparse_weight=1.0,
        k=60.0,
    )
    assert weighted.to_dict()["strategy"] == "weighted_rrf"
    assert event(fusion=weighted).to_dict()["fusion"] == weighted.to_dict()

    with pytest.raises(ValueError, match="non-negative"):
        FusionLogSummary(strategy="weighted_rrf", k=-1.0)
    with pytest.raises(ValueError, match="finite"):
        FusionLogSummary(strategy="weighted_rrf", k=float("nan"))
    with pytest.raises(ValueError, match="strategy"):
        FusionLogSummary(strategy="other")


def test_loggers_and_safe_log_behaviour(caplog: pytest.LogCaptureFixture) -> None:
    built = event()
    NullRetrievalLogger().log_event(built)

    memory = InMemoryRetrievalLogger()
    memory.log_event(built)
    assert memory.events == [built]

    caplog.set_level(logging.INFO, logger="test.retrieval")
    PythonLoggingRetrievalLogger(logger_name="test.retrieval").log_event(built)
    assert any('"event_id": "event-1"' in record.message for record in caplog.records)

    safe_log_retrieval_event(BadLogger(), built)


def test_loguru_logger_with_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict[str, object], str, str]] = []

    class FakeBoundLogger:
        def __init__(self, bound: dict[str, object]) -> None:
            self.bound = bound

        def log(self, level: str, message: str) -> None:
            calls.append((self.bound, level, message))

    class FakeLoguruLogger:
        def bind(self, **kwargs: object) -> FakeBoundLogger:
            return FakeBoundLogger(dict(kwargs))

    import loguru

    monkeypatch.setattr(loguru, "logger", FakeLoguruLogger())
    LoguruRetrievalLogger().log_event(event())

    assert calls[0][0]["event_id"] == "event-1"
    assert calls[0][1] == "INFO"
    assert calls[0][2] == "retrieval_event"


def test_otel_fields_are_validated_and_serialized() -> None:
    built = event(
        otelTraceID="trace-1",
        otelSpanID="span-1",
        otelServiceName="svc",
        otelTraceSampled=True,
    )
    payload = built.to_dict()

    assert payload["otelTraceID"] == "trace-1"
    assert payload["otelSpanID"] == "span-1"
    assert payload["otelServiceName"] == "svc"
    assert payload["otelTraceSampled"] is True

    with pytest.raises(ValueError, match="otelTraceID"):
        event(otelTraceID="bad\x00trace")


@pytest.mark.asyncio
async def test_hybrid_retriever_emits_hybrid_event() -> None:
    logger = InMemoryRetrievalLogger()
    retriever = make_retriever(mode=RetrievalMode.HYBRID, logger=logger)

    result = await retriever.retrieve("consulta privada")

    assert len(result.results) == 1
    assert len(logger.events) == 1
    logged = logger.events[0].to_dict()
    assert logged["mode"] == "hybrid"
    assert logged["fusion"] == {
        "strategy": "weighted_rrf",
        "profile": "default",
        "dense_weight": 1.0,
        "sparse_weight": 1.0,
        "k": 60.0,
    }
    assert logged["chunks_returned"] == len(result.results)
    assert "consulta privada" not in event_to_json(logger.events[0])


@pytest.mark.asyncio
async def test_hybrid_retriever_dense_only_event_and_logger_failure_safe() -> None:
    logger = InMemoryRetrievalLogger()
    retriever = make_retriever(mode=RetrievalMode.DENSE_ONLY, logger=logger)

    result = await retriever.retrieve("consulta privada")

    assert len(result.results) == 1
    logged = logger.events[0].to_dict()
    assert logged["mode"] == "dense_only"
    assert logged["embed_sparse_ms"] == 0.0
    assert logged["fusion"] == {
        "strategy": "none",
        "profile": None,
        "dense_weight": None,
        "sparse_weight": None,
        "k": None,
    }

    failing = make_retriever(mode=RetrievalMode.HYBRID, logger=BadLogger())
    assert (await failing.retrieve("consulta privada")).results


def test_event_output_has_no_forbidden_keys_or_sensitive_text() -> None:
    built = build_retrieval_event(
        query="texto privado que nunca deve aparecer",
        mode="hybrid",
        embed_dense_ms=1.0,
        embed_sparse_ms=1.0,
        search_ms=1.0,
        total_ms=3.0,
        top_k_scores=(0.9,),
        fusion=FusionLogSummary(strategy="weighted_rrf"),
        chunks_returned=1,
    )
    payload = built.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "texto privado" not in serialized
    assert FORBIDDEN_LOG_KEYS.isdisjoint(payload.keys())
    assert "payload" not in serialized
    assert "embedding" not in serialized
    assert "vector" not in serialized
    assert "prompt" not in serialized
    assert "answer" not in serialized


def test_retrieval_logger_static_guards() -> None:
    source = Path(retrieval_logger_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    forbidden_imports = {"qdrant_client", "fastapi", "mcp", "random"}
    forbidden_calls = {"uuid4", "basicConfig", "print", "open", "read", "write"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    assert key.value not in FORBIDDEN_LOG_KEYS, (
                        f"forbidden key in dict literal: {key.value!r}"
                    )

    assert imported_roots.isdisjoint(forbidden_imports)


def test_event_dict_keys_do_not_use_forbidden_log_keys() -> None:
    payload = event().to_dict()

    assert FORBIDDEN_LOG_KEYS.isdisjoint(payload.keys())
    assert FORBIDDEN_LOG_KEYS.isdisjoint(cast(Mapping[str, object], payload["fusion"]).keys())
    assert FORBIDDEN_LOG_KEYS.isdisjoint(
        cast(Mapping[str, object], payload["score_stats"]).keys()
    )


def test_forbidden_key_validation_recurses_into_list_of_dicts() -> None:
    with pytest.raises(ValueError, match="forbidden log key"):
        retrieval_logger_module._validate_no_forbidden_keys(
            {"safe": [{"payload": "blocked"}]}
        )
