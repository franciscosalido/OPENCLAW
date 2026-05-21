"""Master Senior TDD suite — PR-08 AsyncHybridRetriever.

50 tests across 3 categories:
  Passive  (A01–A07): AST purity, contracts, __all__, serialization, validation
  Active   (B01–B33): retrieve with fakes, concurrency, timeout, modes, threshold
  Eccentric(C01–C10): edge cases — null bytes, large ranks, zero weights, NaN clock

Constraints enforced by this file:
  - No qdrant_client import (verified by A02 + B33)
  - No Docker, Ollama, FastAPI, MCP, network, files
  - RRFFusion.fuse called synchronously (verified by B20/SpyFusion)
  - asyncio.gather for parallel embedding and search (verified by B21/B22)
  - Errors sanitized — no query/payload leak (verified by B25/B26/B27)

Run:
  uv run pytest tests/unit/test_hybrid_retriever.py -v
  uv run mypy --strict backend/rag/hybrid_retriever.py tests/unit/test_hybrid_retriever.py
  uv run pyright backend/rag/hybrid_retriever.py tests/unit/test_hybrid_retriever.py
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest

import backend.rag.hybrid_retriever as hr_module
from backend.rag.fusion import FusedResult, RRFFusion, RRFWeightProfile, RankedResult
from backend.rag.hybrid_retriever import (
    AsyncHybridRetriever,
    ClockProtocol,
    DenseEmbedderProtocol,
    DenseSearcherProtocol,
    HybridRetrievalError,
    HybridRetrievalResult,
    HybridRetrievalTrace,
    HybridRetrieverConfig,
    RetrievalMode,
    SearchHit,
    SparseEmbedderProtocol,
    SparseSearcherProtocol,
)
from backend.rag.sparse_vector import SparseVector

# ===========================================================================
# ── Clocks ───────────────────────────────────────────────────────────────────
# ===========================================================================

class FakeClock:
    """Returns values from a pre-set list. Raises StopIteration if exhausted."""

    def __init__(self, values: list[float]) -> None:
        self._it = iter(values)

    def perf_counter(self) -> float:
        return next(self._it)


class IncrementalClock:
    """Monotonically increasing clock; advances by *step* on every call."""

    def __init__(self, start: float = 0.0, step: float = 0.001) -> None:
        self._current = start
        self._step = step

    def reset(self, start: float = 0.0) -> None:
        self._current = start

    def perf_counter(self) -> float:
        val = self._current
        self._current += self._step
        return val


class InfClock:
    """Clock that always returns +inf — triggers _elapsed_ms guard."""

    def perf_counter(self) -> float:
        return float("inf")


# ===========================================================================
# ── Embedders ────────────────────────────────────────────────────────────────
# ===========================================================================

_DEFAULT_DENSE_VEC: list[float] = [0.1, 0.2, 0.3]
_DEFAULT_SPARSE_VEC: SparseVector = SparseVector(indices=[1, 5], values=[0.4, 0.6])


class FakeDenseEmbedder:
    """Async dense embedder with configurable vector, exception, and Event gate."""

    def __init__(
        self,
        vector: list[float] | None = None,
        exc: Exception | None = None,
        started: asyncio.Event | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self._vector = list(vector) if vector is not None else list(_DEFAULT_DENSE_VEC)
        self._exc = exc
        self._started = started
        self._gate = gate
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._started is not None:
            self._started.set()
        if self._gate is not None:
            await self._gate.wait()
        if self._exc is not None:
            raise self._exc
        return list(self._vector)


class FakeSparseEmbedder:
    """Async sparse embedder with configurable vector, exception, and Event gate."""

    def __init__(
        self,
        vector: SparseVector | None = None,
        exc: Exception | None = None,
        started: asyncio.Event | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self._vector = vector if vector is not None else _DEFAULT_SPARSE_VEC
        self._exc = exc
        self._started = started
        self._gate = gate
        self.calls: list[str] = []

    async def embed(self, text: str) -> SparseVector:
        self.calls.append(text)
        if self._started is not None:
            self._started.set()
        if self._gate is not None:
            await self._gate.wait()
        if self._exc is not None:
            raise self._exc
        return self._vector


# ===========================================================================
# ── Searchers ────────────────────────────────────────────────────────────────
# ===========================================================================

@dataclass
class _SearchCall:
    collection_name: str
    vector_name: str
    limit: int
    min_score: float | None


class FakeDenseSearcher:
    """Records search_dense calls and returns pre-configured hits."""

    def __init__(
        self,
        hits: list[SearchHit] | None = None,
        exc: Exception | None = None,
        started: asyncio.Event | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self._hits = hits or []
        self._exc = exc
        self._started = started
        self._gate = gate
        self.calls: list[_SearchCall] = []

    async def search_dense(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: list[float],
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        self.calls.append(
            _SearchCall(
                collection_name=collection_name,
                vector_name=vector_name,
                limit=limit,
                min_score=min_score,
            )
        )
        if self._started is not None:
            self._started.set()
        if self._gate is not None:
            await self._gate.wait()
        if self._exc is not None:
            raise self._exc
        return list(self._hits)


class FakeSparseSearcher:
    """Records search_sparse calls and returns pre-configured hits."""

    def __init__(
        self,
        hits: list[SearchHit] | None = None,
        exc: Exception | None = None,
        started: asyncio.Event | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self._hits = hits or []
        self._exc = exc
        self._started = started
        self._gate = gate
        self.calls: list[_SearchCall] = []

    async def search_sparse(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: SparseVector,
        limit: int,
        min_score: float | None = None,
    ) -> Sequence[SearchHit]:
        self.calls.append(
            _SearchCall(
                collection_name=collection_name,
                vector_name=vector_name,
                limit=limit,
                min_score=min_score,
            )
        )
        if self._started is not None:
            self._started.set()
        if self._gate is not None:
            await self._gate.wait()
        if self._exc is not None:
            raise self._exc
        return list(self._hits)


# ===========================================================================
# ── SpyFusion ────────────────────────────────────────────────────────────────
# ===========================================================================

class SpyFusion:
    """Synchronous (non-async) fusion spy for test B20."""

    def __init__(self, returns: list[FusedResult] | None = None) -> None:
        self._returns: list[FusedResult] = returns or []
        self.fuse_calls: list[dict[str, Any]] = []

    def fuse(
        self,
        *,
        dense_results: Sequence[RankedResult],
        sparse_results: Sequence[RankedResult],
        limit: int | None = None,
    ) -> list[FusedResult]:
        self.fuse_calls.append(
            {
                "dense_results": list(dense_results),
                "sparse_results": list(sparse_results),
                "limit": limit,
            }
        )
        return list(self._returns)


# ===========================================================================
# ── Guarded fakes (must NOT be called during retrieve) ───────────────────────
# ===========================================================================

class GuardedDenseSearcher(FakeDenseSearcher):
    """Fails immediately if any mutation method is called."""

    def create_collection(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call create_collection")

    def upsert(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call upsert")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call delete")


class GuardedSparseSearcher(FakeSparseSearcher):
    def create_collection(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call create_collection")

    def upsert(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call upsert")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("retriever must not call delete")


# ===========================================================================
# ── Builders ──────────────────────────────────────────────────────────────────
# ===========================================================================

def make_config(**overrides: Any) -> HybridRetrieverConfig:
    defaults: dict[str, Any] = {
        "collection_name": "quimera_knowledge_v2",
        "dense_vector_name": "dense",
        "sparse_vector_name": "sparse",
    }
    defaults.update(overrides)
    return HybridRetrieverConfig(**defaults)


def make_retriever(
    *,
    dense_embedder: Any = None,
    sparse_embedder: Any = None,
    dense_searcher: Any = None,
    sparse_searcher: Any = None,
    config: HybridRetrieverConfig | None = None,
    fusion: Any = None,
    clock: Any = None,
) -> AsyncHybridRetriever:
    return AsyncHybridRetriever(
        dense_embedder=dense_embedder or FakeDenseEmbedder(),
        sparse_embedder=sparse_embedder or FakeSparseEmbedder(),
        dense_searcher=dense_searcher or FakeDenseSearcher(),
        sparse_searcher=sparse_searcher or FakeSparseSearcher(),
        config=config or make_config(),
        fusion=fusion or RRFFusion(),
        clock=clock or IncrementalClock(),
    )


def hit(
    result_id: str,
    doc_id: str,
    score: float | None = 1.0,
    extra: dict[str, object] | None = None,
) -> SearchHit:
    payload: dict[str, object] = {"doc_id": doc_id}
    if extra:
        payload.update(extra)
    return SearchHit(result_id=result_id, score=score, payload=payload)


# ===========================================================================
# ── A: PASSIVE (1–7) ─────────────────────────────────────────────────────────
# ===========================================================================

# A01
def test_hybrid_retriever_module_has_no_qdrant_fastapi_mcp_imports() -> None:
    """Production module must not import forbidden packages."""
    source = inspect.getsource(hr_module)
    tree = ast.parse(source)
    forbidden = {"qdrant_client", "fastapi", "mcp", "requests", "httpx", "torch", "numpy"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    violations = imported & forbidden
    assert not violations, f"Forbidden imports found: {violations}"


# A02
def test_unit_tests_do_not_import_qdrant_client() -> None:
    """This test file itself must not import qdrant_client."""
    with open(__file__) as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "qdrant_client" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "qdrant_client" not in node.module


# A03
def test_public_exports_are_minimal() -> None:
    """__all__ must contain exactly the specified public names."""
    expected = {
        "AsyncHybridRetriever",
        "HybridRetrieverConfig",
        "HybridRetrievalResult",
        "HybridRetrievalTrace",
        "HybridRetrievalError",
        "RetrievalMode",
        "SearchHit",
        "DenseEmbedderProtocol",
        "SparseEmbedderProtocol",
        "DenseSearcherProtocol",
        "SparseSearcherProtocol",
        "ClockProtocol",
    }
    assert set(hr_module.__all__) == expected


# A04
def test_config_validates_collection_and_vector_names() -> None:
    """HybridRetrieverConfig rejects blank/null-byte collection and vector names."""
    with pytest.raises((ValueError, TypeError)):
        make_config(collection_name="")
    with pytest.raises((ValueError, TypeError)):
        make_config(collection_name="\x00bad")
    with pytest.raises((ValueError, TypeError)):
        make_config(dense_vector_name="")
    with pytest.raises((ValueError, TypeError)):
        make_config(sparse_vector_name="")
    with pytest.raises((ValueError, TypeError)):
        make_config(dense_vector_name="same", sparse_vector_name="same")


# A05
def test_config_validates_limits_scores_and_timeouts() -> None:
    """HybridRetrieverConfig rejects out-of-range numeric parameters."""
    with pytest.raises((ValueError, TypeError)):
        make_config(search_top_k=0)
    with pytest.raises((ValueError, TypeError)):
        make_config(return_top_k=0)
    with pytest.raises((ValueError, TypeError)):
        make_config(dense_min_score=-0.001)
    with pytest.raises((ValueError, TypeError)):
        make_config(sparse_min_score=-1.0)
    with pytest.raises((ValueError, TypeError)):
        make_config(embed_timeout_s=0.0)
    with pytest.raises((ValueError, TypeError)):
        make_config(embed_timeout_s=-1.0)
    with pytest.raises((ValueError, TypeError)):
        make_config(search_timeout_s=0.0)


# A06
def test_search_hit_validates_result_id_score_and_payload_keys() -> None:
    """SearchHit rejects blank/null result_id, non-finite score, non-str payload keys."""
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="", score=0.5, payload={})
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="   ", score=0.5, payload={})
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="\x00uid", score=0.5, payload={})
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="ok", score=float("nan"), payload={})
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="ok", score=float("inf"), payload={})
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="ok", score=0.5, payload={1: "bad_key"})  # type: ignore[dict-item]


# A07
def test_result_to_dict_is_json_friendly_and_does_not_include_query() -> None:
    """to_dict on HybridRetrievalTrace must not expose any sensitive key."""
    from backend.rag.fusion import SOURCE_DENSE
    fused = FusedResult(
        result_id="chunk-x",
        doc_id="doc-x",
        rrf_score=1.0 / 61.0,
        dense_rank=1,
        sparse_rank=None,
        dense_contribution=1.0 / 61.0,
        sparse_contribution=0.0,
        best_rank=1,
        first_seen_order=0,
        sources=frozenset({SOURCE_DENSE}),
    )
    trace = HybridRetrievalTrace(
        mode="hybrid",
        dense_candidates=1,
        sparse_candidates=0,
        dense_filtered_by_threshold=0,
        sparse_filtered_by_threshold=0,
        fused_count=1,
        returned_count=1,
        embed_ms=1.0,
        search_ms=1.0,
        fusion_ms=0.1,
        total_ms=3.0,
    )
    result = HybridRetrievalResult(results=(fused,), trace=trace)
    d = result.to_dict()
    assert "results" in d
    assert "trace" in d
    td = trace.to_dict()
    assert set(td.keys()) == {
        "mode", "dense_candidates", "sparse_candidates",
        "dense_filtered_by_threshold", "sparse_filtered_by_threshold",
        "fused_count", "returned_count",
        "embed_ms", "search_ms", "fusion_ms", "total_ms",
    }
    sensitive = {"query", "embedding", "vector", "prompt", "answer"}
    assert not sensitive & set(td.keys())


# ===========================================================================
# ── B: ACTIVE (8–40) ─────────────────────────────────────────────────────────
# ===========================================================================

# B01
async def test_hybrid_retriever_rejects_empty_query() -> None:
    """retrieve() raises HybridRetrievalError for empty/blank/null-byte queries."""
    r = make_retriever()
    for bad in ("", "   ", "\x00", "\x00query"):
        with pytest.raises(HybridRetrievalError):
            await r.retrieve(bad)


# B02
async def test_hybrid_mode_calls_both_embedders_and_both_searchers() -> None:
    """HYBRID mode must call both embedders and both searchers with correct params."""
    de = FakeDenseEmbedder()
    se = FakeSparseEmbedder()
    ds = FakeDenseSearcher(hits=[hit("c1", "doc-1", 0.9)])
    ss = FakeSparseSearcher(hits=[hit("c1", "doc-1", 5.0)])
    cfg = make_config(mode=RetrievalMode.HYBRID, search_top_k=15)
    r = make_retriever(
        dense_embedder=de, sparse_embedder=se,
        dense_searcher=ds, sparse_searcher=ss,
        config=cfg,
    )
    await r.retrieve("test query")

    assert len(de.calls) == 1
    assert len(se.calls) == 1
    assert len(ds.calls) == 1
    assert len(ss.calls) == 1

    dc = ds.calls[0]
    assert dc.collection_name == "quimera_knowledge_v2"
    assert dc.vector_name == "dense"
    assert dc.limit == 15

    sc = ss.calls[0]
    assert sc.vector_name == "sparse"
    assert sc.limit == 15


# B03
async def test_hybrid_retriever_returns_fused_results() -> None:
    """RRF fusion: chunk-b (both channels) ranks first; fused_count=3."""
    dense_hits = [hit("chunk-a", "doc-a", 0.9), hit("chunk-b", "doc-b", 0.8)]
    sparse_hits = [hit("chunk-b", "doc-b", 12.0), hit("chunk-c", "doc-c", 8.0)]
    cfg = make_config(return_top_k=10)
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
        config=cfg,
    )
    result = await r.retrieve("financial query")

    ids = [fr.result_id for fr in result.results]
    assert ids[0] == "chunk-b", f"Expected chunk-b first, got {ids}"
    assert set(ids) == {"chunk-a", "chunk-b", "chunk-c"}

    chunk_b = next(fr for fr in result.results if fr.result_id == "chunk-b")
    from backend.rag.fusion import SOURCE_DENSE, SOURCE_SPARSE
    assert SOURCE_DENSE in chunk_b.sources and SOURCE_SPARSE in chunk_b.sources

    t = result.trace
    assert t.dense_candidates == 2
    assert t.sparse_candidates == 2
    assert t.fused_count == 3
    assert t.returned_count <= cfg.return_top_k


# B04
async def test_rank_is_derived_from_filtered_position() -> None:
    """Survivor at position 0 after score filter must receive dense_rank=1."""
    dense_hits = [
        hit("hit-a", "doc-a", 0.5),   # filtered out
        hit("hit-b", "doc-b", 0.9),   # position 0 after filter → rank 1
        hit("hit-c", "doc-c", 0.95),  # position 1 after filter → rank 2
    ]
    cfg = make_config(dense_min_score=0.7, return_top_k=10)
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=dense_hits), config=cfg)
    result = await r.retrieve("query")

    hit_b = next((fr for fr in result.results if fr.result_id == "hit-b"), None)
    assert hit_b is not None
    assert hit_b.dense_rank == 1


# B05
async def test_dense_min_score_filters_before_ranking() -> None:
    """dense_min_score=0.8 discards score=0.7 hits; trace reflects filtered count."""
    dense_hits = [
        hit("keep-1", "doc-1", 0.85),
        hit("drop-1", "doc-2", 0.70),
        hit("keep-2", "doc-3", 0.90),
    ]
    sparse_hits = [hit("sp-1", "doc-sp", 3.0)]
    cfg = make_config(dense_min_score=0.8, return_top_k=10)
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
        config=cfg,
    )
    result = await r.retrieve("q")

    t = result.trace
    assert t.dense_candidates == 3
    assert t.dense_filtered_by_threshold == 1
    assert t.sparse_filtered_by_threshold == 0
    assert "drop-1" not in [fr.result_id for fr in result.results]


# B06
async def test_sparse_min_score_filters_before_ranking() -> None:
    """sparse_min_score filters sparse channel independently of dense."""
    sparse_hits = [hit("sp-keep", "doc-s1", 5.0), hit("sp-drop", "doc-s2", 1.0)]
    cfg = make_config(sparse_min_score=3.0, return_top_k=10)
    r = make_retriever(sparse_searcher=FakeSparseSearcher(hits=sparse_hits), config=cfg)
    result = await r.retrieve("q")

    t = result.trace
    assert t.sparse_candidates == 2
    assert t.sparse_filtered_by_threshold == 1
    assert "sp-drop" not in [fr.result_id for fr in result.results]


# B07
async def test_score_none_is_kept_without_min_score() -> None:
    """Hits with score=None are kept when no min_score threshold is configured."""
    dense_hits = [hit("null-score", "doc-n", score=None)]
    cfg = make_config(dense_min_score=None)
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=dense_hits), config=cfg)
    result = await r.retrieve("q")
    assert any(fr.result_id == "null-score" for fr in result.results)


# B08
async def test_score_none_is_filtered_when_min_score_is_set() -> None:
    """Hits with score=None are discarded when min_score is configured."""
    dense_hits = [hit("null-score", "doc-n", score=None), hit("real-score", "doc-r", 0.9)]
    cfg = make_config(dense_min_score=0.5)
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=dense_hits), config=cfg)
    result = await r.retrieve("q")
    ids = [fr.result_id for fr in result.results]
    assert "null-score" not in ids
    assert "real-score" in ids


# B09
async def test_return_top_k_applied_after_fusion() -> None:
    """return_top_k=2 limits final results even when fusion produces more."""
    dense_hits = [hit(f"d{i}", f"doc-{i}", 0.9 - i * 0.01) for i in range(5)]
    sparse_hits = [hit(f"s{i}", f"sp-{i}", 5.0 - i * 0.1) for i in range(5)]
    cfg = make_config(search_top_k=10, return_top_k=2)
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
        config=cfg,
    )
    result = await r.retrieve("q")
    assert len(result.results) == 2
    assert result.trace.returned_count == 2
    assert result.trace.fused_count >= 2


# B10
async def test_two_chunks_same_doc_id_do_not_collapse() -> None:
    """Two chunks from the same doc_id remain distinct in fusion output."""
    dense_hits = [hit("chunk-1", "doc-a", 0.9), hit("chunk-2", "doc-a", 0.8)]
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=dense_hits))
    result = await r.retrieve("q")
    ids = [fr.result_id for fr in result.results]
    assert "chunk-1" in ids and "chunk-2" in ids


# B11
async def test_conflicting_doc_id_for_same_result_id_becomes_hybrid_retrieval_error() -> None:
    """result_id with different doc_id in dense vs sparse raises HybridRetrievalError."""
    dense_hits = [hit("chunk-conflict", "doc-a", 0.9)]
    sparse_hits = [hit("chunk-conflict", "doc-b", 5.0)]
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
    )
    with pytest.raises(HybridRetrievalError):
        await r.retrieve("q")


# B12
async def test_missing_doc_id_in_payload_fails() -> None:
    """SearchHit without doc_id in payload raises HybridRetrievalError."""
    bad_hit = SearchHit(result_id="chunk-x", score=0.9, payload={"other": "value"})
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[bad_hit]))
    with pytest.raises(HybridRetrievalError):
        await r.retrieve("q")


# B13
async def test_dense_only_mode_skips_sparse_embedder_and_sparse_searcher() -> None:
    """DENSE_ONLY: sparse embedder and searcher receive zero calls."""
    de = FakeDenseEmbedder()
    se = FakeSparseEmbedder()
    ds = FakeDenseSearcher(hits=[hit("c1", "doc-1")])
    ss = FakeSparseSearcher()
    cfg = make_config(mode=RetrievalMode.DENSE_ONLY)
    r = make_retriever(
        dense_embedder=de, sparse_embedder=se,
        dense_searcher=ds, sparse_searcher=ss,
        config=cfg,
    )
    result = await r.retrieve("q")
    assert len(de.calls) == 1 and len(se.calls) == 0
    assert len(ds.calls) == 1 and len(ss.calls) == 0
    assert result.trace.sparse_candidates == 0
    assert result.trace.sparse_filtered_by_threshold == 0


# B14
async def test_sparse_only_mode_skips_dense_embedder_and_dense_searcher() -> None:
    """SPARSE_ONLY: dense embedder and searcher receive zero calls."""
    de = FakeDenseEmbedder()
    se = FakeSparseEmbedder()
    ds = FakeDenseSearcher()
    ss = FakeSparseSearcher(hits=[hit("c1", "doc-1")])
    cfg = make_config(mode=RetrievalMode.SPARSE_ONLY)
    r = make_retriever(
        dense_embedder=de, sparse_embedder=se,
        dense_searcher=ds, sparse_searcher=ss,
        config=cfg,
    )
    result = await r.retrieve("q")
    assert len(de.calls) == 0 and len(se.calls) == 1
    assert len(ds.calls) == 0 and len(ss.calls) == 1
    assert result.trace.dense_candidates == 0
    assert result.trace.dense_filtered_by_threshold == 0


# B15
async def test_empty_dense_and_sparse_hits_returns_empty_results() -> None:
    """Both channels empty → results=(), fused_count=0, returned_count=0."""
    r = make_retriever()
    result = await r.retrieve("q")
    assert result.results == ()
    assert result.trace.fused_count == 0
    assert result.trace.returned_count == 0


# B16
async def test_channel_empty_but_other_channel_returns_results() -> None:
    """Dense empty + sparse with hits → sparse-only results via RRF."""
    sparse_hits = [hit("sp-1", "doc-sp", 5.0), hit("sp-2", "doc-sp2", 3.0)]
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=[]),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
    )
    result = await r.retrieve("q")
    from backend.rag.fusion import SOURCE_SPARSE
    assert len(result.results) == 2
    for fr in result.results:
        assert SOURCE_SPARSE in fr.sources


# B17
async def test_raw_scores_do_not_control_fusion_order() -> None:
    """RRF rank governs order; raw score is diagnostic only."""
    dense_hits = [
        hit("chunk-a", "doc-a", 0.01),  # rank 1 dense, very low raw score
        hit("chunk-b", "doc-b", 0.99),  # rank 2 dense, very high raw score
    ]
    sparse_hits = [hit("chunk-b", "doc-b", 99.0)]  # rank 1 sparse
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
    )
    result = await r.retrieve("q")
    # chunk-b is rank 1 in both channels → higher RRF score wins
    assert result.results[0].result_id == "chunk-b"


# B18
async def test_latency_fields_are_non_negative_and_total_is_present() -> None:
    """All latency trace fields must be >= 0.0."""
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=[hit("c1", "doc-1")]),
        clock=IncrementalClock(start=0.0, step=0.001),
    )
    result = await r.retrieve("q")
    t = result.trace
    assert t.embed_ms >= 0.0
    assert t.search_ms >= 0.0
    assert t.fusion_ms >= 0.0
    assert t.total_ms >= 0.0


# B19
async def test_latency_trace_counts_are_correct() -> None:
    """Trace counts must be self-consistent with inputs and return_top_k."""
    dense_hits = [hit("d1", "doc-1", 0.9), hit("d2", "doc-2", 0.8)]
    sparse_hits = [hit("s1", "doc-3", 4.0)]
    cfg = make_config(return_top_k=5)
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
        config=cfg,
    )
    result = await r.retrieve("q")
    t = result.trace
    assert t.dense_candidates == 2
    assert t.sparse_candidates == 1
    assert t.dense_filtered_by_threshold == 0
    assert t.sparse_filtered_by_threshold == 0
    assert t.fused_count == 3
    assert t.returned_count == 3
    assert t.returned_count <= cfg.return_top_k


# B20 — SpyFusion: fuse() must be sync
async def test_fusion_is_called_synchronously_after_search() -> None:
    """fuse() must be a regular sync method; inputs must be RankedResult instances."""
    assert not asyncio.iscoroutinefunction(SpyFusion.fuse), (
        "SpyFusion.fuse must be sync — mirrors the requirement on the production retriever"
    )
    spy = SpyFusion()
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=[hit("c1", "doc-1", 0.9)]),
        fusion=spy,
    )
    await r.retrieve("q")

    assert len(spy.fuse_calls) == 1
    call = spy.fuse_calls[0]
    dense_results = call["dense_results"]
    assert all(isinstance(rr, RankedResult) for rr in dense_results)


# B21 — Concurrency: embedding
async def test_embed_tasks_run_concurrently_in_hybrid_mode() -> None:
    """Dense and sparse embedding must start before either completes."""
    started_dense: asyncio.Event = asyncio.Event()
    started_sparse: asyncio.Event = asyncio.Event()
    gate: asyncio.Event = asyncio.Event()

    r = make_retriever(
        dense_embedder=FakeDenseEmbedder(started=started_dense, gate=gate),
        sparse_embedder=FakeSparseEmbedder(started=started_sparse, gate=gate),
    )
    task: asyncio.Task[HybridRetrievalResult] = asyncio.create_task(r.retrieve("q"))

    await asyncio.wait_for(started_dense.wait(), timeout=2.0)
    await asyncio.wait_for(started_sparse.wait(), timeout=2.0)
    assert started_dense.is_set() and started_sparse.is_set()

    gate.set()
    await asyncio.wait_for(task, timeout=2.0)


# B22 — Concurrency: search
async def test_search_tasks_run_concurrently_in_hybrid_mode() -> None:
    """Dense and sparse search must start before either completes."""
    started_dense: asyncio.Event = asyncio.Event()
    started_sparse: asyncio.Event = asyncio.Event()
    gate: asyncio.Event = asyncio.Event()

    ds = FakeDenseSearcher(hits=[hit("c1", "doc-1")], started=started_dense, gate=gate)
    ss = FakeSparseSearcher(hits=[hit("c1", "doc-1")], started=started_sparse, gate=gate)

    r = make_retriever(dense_searcher=ds, sparse_searcher=ss)
    task: asyncio.Task[HybridRetrievalResult] = asyncio.create_task(r.retrieve("q"))

    await asyncio.wait_for(started_dense.wait(), timeout=2.0)
    await asyncio.wait_for(started_sparse.wait(), timeout=2.0)
    assert started_dense.is_set() and started_sparse.is_set()

    gate.set()
    await asyncio.wait_for(task, timeout=2.0)


# B23
async def test_embed_timeout_raises_hybrid_retrieval_error() -> None:
    """Embedding that never resolves must trigger HybridRetrievalError."""
    never_resolves: asyncio.Event = asyncio.Event()
    de = FakeDenseEmbedder(gate=never_resolves)
    cfg = make_config(embed_timeout_s=0.05)
    r = make_retriever(dense_embedder=de, config=cfg)
    with pytest.raises(HybridRetrievalError, match="timed out|failed"):
        await asyncio.wait_for(r.retrieve("q"), timeout=2.0)


# B24
async def test_search_timeout_raises_hybrid_retrieval_error() -> None:
    """Search that never resolves must trigger HybridRetrievalError."""
    never_resolves: asyncio.Event = asyncio.Event()
    ds = FakeDenseSearcher(gate=never_resolves)
    cfg = make_config(mode=RetrievalMode.DENSE_ONLY, search_timeout_s=0.05)
    r = make_retriever(dense_searcher=ds, config=cfg)
    with pytest.raises(HybridRetrievalError, match="timed out|failed"):
        await asyncio.wait_for(r.retrieve("q"), timeout=2.0)


# B25
async def test_dependency_exception_is_wrapped_without_query_or_payload_leak() -> None:
    """Dependency exceptions must not leak query text or raw vectors."""
    secret_query = "top-secret-financial-query"
    de = FakeDenseEmbedder(
        exc=RuntimeError(f"contains: {secret_query} vector=[0.1,0.2]")
    )
    cfg = make_config(mode=RetrievalMode.DENSE_ONLY)
    r = make_retriever(dense_embedder=de, config=cfg)

    with pytest.raises(HybridRetrievalError) as exc_info:
        await r.retrieve(secret_query)

    error_text = str(exc_info.value).lower()
    assert secret_query.lower() not in error_text
    assert "vector=" not in error_text


# B26
async def test_result_trace_does_not_include_sensitive_fields() -> None:
    """trace.to_dict() must not contain query, text, embedding, or similar keys."""
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[hit("c1", "doc-1")]))
    result = await r.retrieve("sensitive query")
    td = result.trace.to_dict()
    forbidden_keys = {"query", "text", "chunk_text", "vector", "embedding", "prompt", "answer"}
    assert not forbidden_keys & set(td.keys())


# B27
async def test_payload_text_not_in_trace() -> None:
    """Payload 'text' field must not propagate into trace.to_dict()."""
    h = hit("c1", "doc-1", 0.9, extra={"text": "This is the chunk content."})
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[h]))
    result = await r.retrieve("q")
    td = result.trace.to_dict()
    assert "text" not in td
    assert "chunk content" not in str(td).lower()


# B28
async def test_determinism_across_repeated_calls() -> None:
    """Same inputs produce identical fused result ordering across two calls."""
    dense_hits = [hit("chunk-a", "doc-a", 0.9), hit("chunk-b", "doc-b", 0.8)]
    sparse_hits = [hit("chunk-b", "doc-b", 5.0), hit("chunk-c", "doc-c", 3.0)]

    def make_r() -> AsyncHybridRetriever:
        return make_retriever(
            dense_searcher=FakeDenseSearcher(hits=list(dense_hits)),
            sparse_searcher=FakeSparseSearcher(hits=list(sparse_hits)),
            clock=IncrementalClock(),
        )

    res1 = await make_r().retrieve("q")
    res2 = await make_r().retrieve("q")

    assert [fr.result_id for fr in res1.results] == [fr.result_id for fr in res2.results]
    assert [fr.rrf_score for fr in res1.results] == [fr.rrf_score for fr in res2.results]


# B29
async def test_mode_override_per_retrieve() -> None:
    """Config override on a single call must not mutate the instance config."""
    de = FakeDenseEmbedder()
    se = FakeSparseEmbedder()
    ds = FakeDenseSearcher(hits=[hit("c1", "doc-1")])
    ss = FakeSparseSearcher()
    instance_cfg = make_config(mode=RetrievalMode.HYBRID)
    override_cfg = make_config(mode=RetrievalMode.DENSE_ONLY)

    r = make_retriever(
        dense_embedder=de, sparse_embedder=se,
        dense_searcher=ds, sparse_searcher=ss,
        config=instance_cfg,
    )
    await r.retrieve("q", config=override_cfg)

    assert len(se.calls) == 0 and len(ss.calls) == 0
    assert r.config.mode is RetrievalMode.HYBRID


# B30
async def test_custom_rrf_profile_changes_order() -> None:
    """Dense-heavy profile must promote dense-only results above sparse-only."""
    dense_hits = [hit("dense-only", "doc-d", 0.9)]
    sparse_hits = [hit("sparse-only", "doc-s", 9.0)]

    sparse_heavy = RRFFusion(
        profile=RRFWeightProfile(dense_weight=1.0, sparse_weight=100.0, name="sparse-heavy")
    )
    r_sh = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=list(dense_hits)),
        sparse_searcher=FakeSparseSearcher(hits=list(sparse_hits)),
        fusion=sparse_heavy,
    )
    res_sh = await r_sh.retrieve("q")
    assert res_sh.results[0].result_id == "sparse-only"

    dense_heavy = RRFFusion(
        profile=RRFWeightProfile(dense_weight=100.0, sparse_weight=1.0, name="dense-heavy")
    )
    r_dh = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=list(dense_hits)),
        sparse_searcher=FakeSparseSearcher(hits=list(sparse_hits)),
        fusion=dense_heavy,
    )
    res_dh = await r_dh.retrieve("q")
    assert res_dh.results[0].result_id == "dense-only"


# B31
async def test_no_collection_mutation_methods_are_called() -> None:
    """retrieve() must never call create_collection, upsert, or delete on fakes."""
    ds = GuardedDenseSearcher(hits=[hit("c1", "doc-1")])
    ss = GuardedSparseSearcher(hits=[hit("c1", "doc-1")])
    r = make_retriever(dense_searcher=ds, sparse_searcher=ss)
    result = await r.retrieve("q")
    assert result is not None


# B32
def test_qdrant_native_prefetch_is_not_used_in_v0() -> None:
    """DenseSearcherProtocol and SparseSearcherProtocol must not define 'prefetch'."""
    source = inspect.getsource(hr_module)
    # No 'prefetch' string anywhere in the production source
    assert "prefetch" not in source
    # Protocol inspection
    for protocol_cls in (DenseSearcherProtocol, SparseSearcherProtocol):
        methods = [
            name for name, _ in inspect.getmembers(protocol_cls)
            if not name.startswith("__")
        ]
        assert "prefetch" not in methods


# B33
def test_hybrid_retriever_does_not_create_client() -> None:
    """Production module must not import or instantiate qdrant_client."""
    source = inspect.getsource(hr_module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "qdrant_client" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "qdrant_client" not in node.module
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in ("QdrantClient", "AsyncQdrantClient")


# ===========================================================================
# ── C: ECCENTRIC (41–50) ──────────────────────────────────────────────────────
# ===========================================================================

# C01
async def test_duplicate_result_id_same_doc_id_across_channels_fuses() -> None:
    """Same result_id + doc_id in both channels → single result with both sources."""
    dense_hits = [hit("chunk-dup", "doc-dup", 0.9)]
    sparse_hits = [hit("chunk-dup", "doc-dup", 5.0)]
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
    )
    result = await r.retrieve("q")
    assert len(result.results) == 1
    fr = result.results[0]
    assert fr.result_id == "chunk-dup"
    from backend.rag.fusion import SOURCE_DENSE, SOURCE_SPARSE
    assert SOURCE_DENSE in fr.sources and SOURCE_SPARSE in fr.sources


# C02
async def test_duplicate_result_id_within_same_channel_uses_first_occurrence() -> None:
    """Duplicate result_id in one channel → first occurrence kept at rank 1."""
    dense_hits = [
        hit("dup-id", "doc-a", 0.9),
        hit("unique", "doc-b", 0.8),
        hit("dup-id", "doc-a", 0.7),  # second occurrence — must be ignored by fusion
    ]
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=dense_hits))
    result = await r.retrieve("q")
    ids = [fr.result_id for fr in result.results]
    assert ids.count("dup-id") == 1
    dup = next(fr for fr in result.results if fr.result_id == "dup-id")
    assert dup.dense_rank == 1


# C03
async def test_large_rank_values_are_supported() -> None:
    """High-rank results must produce finite positive RRF scores without overflow."""
    large_hits = [hit(f"h{i}", f"doc-{i}", 0.5 - i * 0.001) for i in range(50)]
    cfg = make_config(search_top_k=100, return_top_k=10)
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=large_hits), config=cfg)
    result = await r.retrieve("q")
    assert len(result.results) == 10
    for fr in result.results:
        assert fr.rrf_score > 0.0
        assert math.isfinite(fr.rrf_score)


# C04
async def test_zero_weight_rrf_profile_dense_weight_zero() -> None:
    """dense_weight=0 → dense contributions are 0; sparse result scores dominate."""
    dense_hits = [hit("dense-only", "doc-d", 0.99)]
    sparse_hits = [hit("sparse-only", "doc-s", 1.0)]
    sparse_fusion = RRFFusion(
        profile=RRFWeightProfile(dense_weight=0.0, sparse_weight=1.0, name="sparse-only-weight")
    )
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=dense_hits),
        sparse_searcher=FakeSparseSearcher(hits=sparse_hits),
        fusion=sparse_fusion,
    )
    result = await r.retrieve("q")
    assert "sparse-only" in [fr.result_id for fr in result.results]
    sparse_fr = next(fr for fr in result.results if fr.result_id == "sparse-only")
    assert sparse_fr.dense_contribution == 0.0
    assert sparse_fr.sparse_contribution > 0.0


# C05
async def test_nan_latency_not_possible_with_monotonic_clock() -> None:
    """IncrementalClock guarantees no NaN/negative latencies."""
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=[hit("c1", "doc-1")]),
        clock=IncrementalClock(start=1.0, step=0.001),
    )
    result = await r.retrieve("q")
    t = result.trace
    for field_name in ("embed_ms", "search_ms", "fusion_ms", "total_ms"):
        val = getattr(t, field_name)
        assert math.isfinite(val), f"{field_name} is not finite: {val}"
        assert val >= 0.0, f"{field_name} is negative: {val}"


# C06
async def test_invalid_clock_value_raises_or_clamps() -> None:
    """A clock returning inf must cause HybridRetrievalError or produce clamped latencies."""
    r = make_retriever(
        dense_searcher=FakeDenseSearcher(hits=[hit("c1", "doc-1")]),
        clock=InfClock(),
    )
    try:
        result = await r.retrieve("q")
        t = result.trace
        for field_name in ("embed_ms", "search_ms", "fusion_ms", "total_ms"):
            val = getattr(t, field_name)
            assert math.isfinite(val), f"Expected clamped finite {field_name}, got {val}"
    except HybridRetrievalError:
        pass  # also acceptable


# C07
async def test_payload_doc_id_with_null_byte_fails() -> None:
    """doc_id containing null byte in payload raises HybridRetrievalError."""
    bad_hit = SearchHit(result_id="chunk-ok", score=0.9, payload={"doc_id": "doc\x00a"})
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[bad_hit]))
    with pytest.raises(HybridRetrievalError):
        await r.retrieve("q")


# C08
async def test_payload_doc_id_whitespace_fails() -> None:
    """doc_id that is all whitespace raises HybridRetrievalError."""
    bad_hit = SearchHit(result_id="chunk-ok", score=0.9, payload={"doc_id": "   "})
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[bad_hit]))
    with pytest.raises(HybridRetrievalError):
        await r.retrieve("q")


# C09
def test_result_id_null_byte_in_search_hit_fails_on_construction() -> None:
    """SearchHit with null byte in result_id fails at construction time."""
    with pytest.raises((ValueError, TypeError)):
        SearchHit(result_id="chunk\x00bad", score=0.9, payload={"doc_id": "doc-1"})


# C10 — Snapshot
async def test_to_dict_stable_key_shape_snapshot() -> None:
    """HybridRetrievalResult.to_dict() must have exactly the expected key structure."""
    r = make_retriever(dense_searcher=FakeDenseSearcher(hits=[hit("chunk-snap", "doc-snap", 0.9)]))
    result = await r.retrieve("snapshot query")
    d = result.to_dict()

    assert set(d.keys()) == {"results", "trace"}

    expected_trace_keys = {
        "mode", "dense_candidates", "sparse_candidates",
        "dense_filtered_by_threshold", "sparse_filtered_by_threshold",
        "fused_count", "returned_count",
        "embed_ms", "search_ms", "fusion_ms", "total_ms",
    }
    trace_dict = d["trace"]
    assert isinstance(trace_dict, dict)
    assert set(trace_dict.keys()) == expected_trace_keys

    results_list = d["results"]
    assert isinstance(results_list, list) and len(results_list) >= 1
    expected_result_keys = {
        "result_id", "doc_id", "rrf_score",
        "dense_rank", "sparse_rank",
        "dense_contribution", "sparse_contribution",
        "best_rank", "first_seen_order",
        "dense_raw_score", "sparse_raw_score",
        "sources", "payload",
    }
    assert set(results_list[0].keys()) == expected_result_keys


# ===========================================================================
# ── Skeleton: live Qdrant (skipped, NOT executed by default) ─────────────────
# ===========================================================================
# @pytest.mark.qdrant_live
# @pytest.mark.skip(reason="requires live Qdrant — not part of unit suite")
# async def test_live_hybrid_retriever_smoke() -> None:
#     """End-to-end smoke against a real Qdrant instance."""
#     ...
