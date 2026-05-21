"""Async hybrid retriever for OPENCLAW RAG.

Orchestrates dense + sparse retrieval with Weighted RRF fusion.

Design invariants:
- No qdrant_client import anywhere in this module.
- No network, file I/O, or process spawning.
- All I/O is async (embedding, search, retrieve).
- RRF fusion is always called synchronously.
- Score thresholds are applied per channel after receiving raw hits,
  before assigning ranks and calling fusion.
- Error messages never contain query text, raw vectors, or payload values.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from backend.rag.fusion import (
    FusedResult,
    RRFFusion,
    RankedResult,
    ranked_result_from_position,
)
from backend.rag.sparse_vector import SparseVector


# ---------------------------------------------------------------------------
# Enums and exceptions
# ---------------------------------------------------------------------------
class RetrievalMode(Enum):
    """Retrieval channel selection."""
    HYBRID = "hybrid"
    DENSE_ONLY = "dense_only"
    SPARSE_ONLY = "sparse_only"


class HybridRetrievalError(Exception):
    """Sanitized retrieval error — never contains query text or raw vectors."""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------
@runtime_checkable
class ClockProtocol(Protocol):
    def perf_counter(self) -> float: ...


@runtime_checkable
class DenseEmbedderProtocol(Protocol):
    async def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class SparseEmbedderProtocol(Protocol):
    async def embed(self, text: str) -> SparseVector: ...


@runtime_checkable
class DenseSearcherProtocol(Protocol):
    async def search_dense(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: list[float],
        limit: int,
        min_score: float | None = None,
    ) -> Sequence["SearchHit"]: ...


@runtime_checkable
class SparseSearcherProtocol(Protocol):
    async def search_sparse(
        self,
        *,
        collection_name: str,
        vector_name: str,
        vector: SparseVector,
        limit: int,
        min_score: float | None = None,
    ) -> Sequence["SearchHit"]: ...


# ---------------------------------------------------------------------------
# SearchHit value type
# ---------------------------------------------------------------------------
def _validate_result_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("result_id must be a string")
    if "\x00" in value:
        raise ValueError("result_id cannot contain null bytes")
    if not value.strip():
        raise ValueError("result_id cannot be blank")
    return value


@dataclass(frozen=True)
class SearchHit:
    """One hit returned by a searcher before RRF fusion.

    result_id is the Qdrant point UUID (chunk id, not doc_id).
    score may be None when the searcher does not provide a relevance estimate.
    Payload must contain 'doc_id' for the retriever to build RankedResult objects.
    """
    result_id: str
    score: float | None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        clean_id = _validate_result_id(self.result_id)
        object.__setattr__(self, "result_id", clean_id)

        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
                raise TypeError("score must be numeric or None")
            fv = float(self.score)
            if not math.isfinite(fv):
                raise ValueError("score must be finite or None")
            object.__setattr__(self, "score", fv)

        for key in self.payload:
            if not isinstance(key, str):
                raise TypeError("payload keys must be strings")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HybridRetrieverConfig:
    """Immutable retrieval configuration."""
    collection_name: str
    dense_vector_name: str
    sparse_vector_name: str
    mode: RetrievalMode = RetrievalMode.HYBRID
    search_top_k: int = 20
    return_top_k: int = 10
    dense_min_score: float | None = None
    sparse_min_score: float | None = None
    embed_timeout_s: float = 5.0
    search_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            raise ValueError("collection_name cannot be blank")
        if "\x00" in self.collection_name:
            raise ValueError("collection_name cannot contain null bytes")
        if not self.dense_vector_name:
            raise ValueError("dense_vector_name cannot be empty")
        if not self.sparse_vector_name:
            raise ValueError("sparse_vector_name cannot be empty")
        if self.dense_vector_name == self.sparse_vector_name:
            raise ValueError("dense_vector_name and sparse_vector_name must differ")
        if isinstance(self.search_top_k, bool) or not isinstance(self.search_top_k, int):
            raise TypeError("search_top_k must be an integer")
        if self.search_top_k <= 0:
            raise ValueError("search_top_k must be >= 1")
        if isinstance(self.return_top_k, bool) or not isinstance(self.return_top_k, int):
            raise TypeError("return_top_k must be an integer")
        if self.return_top_k <= 0:
            raise ValueError("return_top_k must be >= 1")
        if self.dense_min_score is not None and float(self.dense_min_score) < 0.0:
            raise ValueError("dense_min_score must be non-negative")
        if self.sparse_min_score is not None and float(self.sparse_min_score) < 0.0:
            raise ValueError("sparse_min_score must be non-negative")
        if float(self.embed_timeout_s) <= 0.0:
            raise ValueError("embed_timeout_s must be > 0")
        if float(self.search_timeout_s) <= 0.0:
            raise ValueError("search_timeout_s must be > 0")


# ---------------------------------------------------------------------------
# Trace and result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HybridRetrievalTrace:
    """Diagnostic counters and latency breakdown.
    Does not contain query text, vectors, embeddings, or any payload value.
    """
    mode: str
    dense_candidates: int
    sparse_candidates: int
    dense_filtered_by_threshold: int
    sparse_filtered_by_threshold: int
    fused_count: int
    returned_count: int
    embed_ms: float
    search_ms: float
    fusion_ms: float
    total_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "dense_candidates": self.dense_candidates,
            "sparse_candidates": self.sparse_candidates,
            "dense_filtered_by_threshold": self.dense_filtered_by_threshold,
            "sparse_filtered_by_threshold": self.sparse_filtered_by_threshold,
            "fused_count": self.fused_count,
            "returned_count": self.returned_count,
            "embed_ms": self.embed_ms,
            "search_ms": self.search_ms,
            "fusion_ms": self.fusion_ms,
            "total_ms": self.total_ms,
        }


@dataclass(frozen=True)
class HybridRetrievalResult:
    """Output of one retrieve() call."""
    results: tuple[FusedResult, ...]
    trace: HybridRetrievalTrace

    def to_dict(self) -> dict[str, object]:
        return {
            "results": [r.to_dict() for r in self.results],
            "trace": self.trace.to_dict(),
        }


# ---------------------------------------------------------------------------
# Default clock (real; swapped in tests)
# ---------------------------------------------------------------------------
class _RealClock:
    def perf_counter(self) -> float:
        return time.perf_counter()


_DEFAULT_CLOCK: ClockProtocol = _RealClock()


# ---------------------------------------------------------------------------
# Async retriever
# ---------------------------------------------------------------------------
@dataclass
class AsyncHybridRetriever:
    """Async retrieval orchestrator: embed -> search -> filter -> rank -> fuse.

    All I/O calls (embedding, search) are async. RRF fusion is always
    invoked synchronously after both search channels return.
    """
    dense_embedder: DenseEmbedderProtocol
    sparse_embedder: SparseEmbedderProtocol
    dense_searcher: DenseSearcherProtocol
    sparse_searcher: SparseSearcherProtocol
    config: HybridRetrieverConfig
    fusion: RRFFusion = field(default_factory=RRFFusion)
    clock: ClockProtocol = field(default_factory=lambda: _DEFAULT_CLOCK)

    async def retrieve(
        self,
        query: str,
        *,
        config: HybridRetrieverConfig | None = None,
    ) -> HybridRetrievalResult:
        """Execute a retrieval query and return fused results with trace."""
        _validate_query(query)
        cfg = config if config is not None else self.config
        t0 = self.clock.perf_counter()
        try:
            return await self._do_retrieve(query, cfg, t0)
        except HybridRetrievalError:
            raise
        except ValueError:
            raise HybridRetrievalError("retrieval failed: invalid result data") from None
        except Exception:
            raise HybridRetrievalError("retrieval failed") from None

    async def _do_retrieve(
        self,
        query: str,
        cfg: HybridRetrieverConfig,
        t0: float,
    ) -> HybridRetrievalResult:
        mode = cfg.mode

        # -- Embedding (concurrent in HYBRID) --
        t_embed = self.clock.perf_counter()
        dense_vec: list[float] | None = None
        sparse_vec: SparseVector | None = None

        if mode is RetrievalMode.HYBRID:
            d_emb: asyncio.Task[list[float]] = asyncio.create_task(
                self._embed_dense(query, cfg)
            )
            s_emb: asyncio.Task[SparseVector] = asyncio.create_task(
                self._embed_sparse(query, cfg)
            )
            dense_vec, sparse_vec = await asyncio.gather(d_emb, s_emb)
        elif mode is RetrievalMode.DENSE_ONLY:
            dense_vec = await self._embed_dense(query, cfg)
        else:
            sparse_vec = await self._embed_sparse(query, cfg)

        embed_ms = _elapsed_ms(t_embed, self.clock.perf_counter())

        # -- Search (concurrent in HYBRID) --
        t_search = self.clock.perf_counter()
        dense_hits: Sequence[SearchHit] = ()
        sparse_hits: Sequence[SearchHit] = ()

        if mode is RetrievalMode.HYBRID:
            assert dense_vec is not None
            assert sparse_vec is not None
            d_srch: asyncio.Task[Sequence[SearchHit]] = asyncio.create_task(
                self._search_dense(dense_vec, cfg)
            )
            s_srch: asyncio.Task[Sequence[SearchHit]] = asyncio.create_task(
                self._search_sparse(sparse_vec, cfg)
            )
            dense_hits, sparse_hits = await asyncio.gather(d_srch, s_srch)
        elif mode is RetrievalMode.DENSE_ONLY:
            assert dense_vec is not None
            dense_hits = await self._search_dense(dense_vec, cfg)
        else:
            assert sparse_vec is not None
            sparse_hits = await self._search_sparse(sparse_vec, cfg)

        search_ms = _elapsed_ms(t_search, self.clock.perf_counter())

        # -- Per-channel score filtering (before ranking) --
        dense_raw = len(dense_hits)
        sparse_raw = len(sparse_hits)

        dense_passed = _filter_by_score(list(dense_hits), cfg.dense_min_score)
        sparse_passed = _filter_by_score(list(sparse_hits), cfg.sparse_min_score)

        dense_filtered_n = dense_raw - len(dense_passed)
        sparse_filtered_n = sparse_raw - len(sparse_passed)

        # -- Convert to RankedResult (rank = 1-based position after filter) --
        dense_ranked = _hits_to_ranked(dense_passed)
        sparse_ranked = _hits_to_ranked(sparse_passed)

        # -- RRF Fusion (synchronous) --
        t_fuse = self.clock.perf_counter()
        all_fused = self.fusion.fuse(
            dense_results=dense_ranked,
            sparse_results=sparse_ranked,
            limit=None,
        )
        fusion_ms = _elapsed_ms(t_fuse, self.clock.perf_counter())

        fused_count = len(all_fused)
        final: tuple[FusedResult, ...] = tuple(all_fused[: cfg.return_top_k])
        total_ms = _elapsed_ms(t0, self.clock.perf_counter())

        trace = HybridRetrievalTrace(
            mode=mode.value,
            dense_candidates=dense_raw,
            sparse_candidates=sparse_raw,
            dense_filtered_by_threshold=dense_filtered_n,
            sparse_filtered_by_threshold=sparse_filtered_n,
            fused_count=fused_count,
            returned_count=len(final),
            embed_ms=embed_ms,
            search_ms=search_ms,
            fusion_ms=fusion_ms,
            total_ms=total_ms,
        )
        return HybridRetrievalResult(results=final, trace=trace)

    async def _embed_dense(self, query: str, cfg: HybridRetrieverConfig) -> list[float]:
        try:
            return await asyncio.wait_for(
                self.dense_embedder.embed(query), timeout=cfg.embed_timeout_s
            )
        except asyncio.TimeoutError:
            raise HybridRetrievalError("dense embedding timed out") from None
        except HybridRetrievalError:
            raise
        except Exception:
            raise HybridRetrievalError("dense embedding failed") from None

    async def _embed_sparse(self, query: str, cfg: HybridRetrieverConfig) -> SparseVector:
        try:
            return await asyncio.wait_for(
                self.sparse_embedder.embed(query), timeout=cfg.embed_timeout_s
            )
        except asyncio.TimeoutError:
            raise HybridRetrievalError("sparse embedding timed out") from None
        except HybridRetrievalError:
            raise
        except Exception:
            raise HybridRetrievalError("sparse embedding failed") from None

    async def _search_dense(
        self, vec: list[float], cfg: HybridRetrieverConfig
    ) -> Sequence[SearchHit]:
        try:
            return await asyncio.wait_for(
                self.dense_searcher.search_dense(
                    collection_name=cfg.collection_name,
                    vector_name=cfg.dense_vector_name,
                    vector=vec,
                    limit=cfg.search_top_k,
                    min_score=cfg.dense_min_score,
                ),
                timeout=cfg.search_timeout_s,
            )
        except asyncio.TimeoutError:
            raise HybridRetrievalError("dense search timed out") from None
        except HybridRetrievalError:
            raise
        except Exception:
            raise HybridRetrievalError("dense search failed") from None

    async def _search_sparse(
        self, vec: SparseVector, cfg: HybridRetrieverConfig
    ) -> Sequence[SearchHit]:
        try:
            return await asyncio.wait_for(
                self.sparse_searcher.search_sparse(
                    collection_name=cfg.collection_name,
                    vector_name=cfg.sparse_vector_name,
                    vector=vec,
                    limit=cfg.search_top_k,
                    min_score=cfg.sparse_min_score,
                ),
                timeout=cfg.search_timeout_s,
            )
        except asyncio.TimeoutError:
            raise HybridRetrievalError("sparse search timed out") from None
        except HybridRetrievalError:
            raise
        except Exception:
            raise HybridRetrievalError("sparse search failed") from None


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------
def _validate_query(query: str) -> None:
    if not isinstance(query, str) or "\x00" in query or not query.strip():
        raise HybridRetrievalError(
            "query is invalid: empty, blank, or contains forbidden characters"
        )


def _elapsed_ms(t_start: float, t_end: float) -> float:
    if not math.isfinite(t_start) or not math.isfinite(t_end):
        raise ValueError("clock returned non-finite timestamp")
    return max(0.0, (t_end - t_start) * 1000.0)


def _filter_by_score(hits: list[SearchHit], min_score: float | None) -> list[SearchHit]:
    """Filter hits by score threshold; score=None hits are kept only when no threshold."""
    if min_score is None:
        return hits
    return [h for h in hits if h.score is not None and h.score >= min_score]


def _hits_to_ranked(hits: list[SearchHit]) -> list[RankedResult]:
    """Convert filtered SearchHits to RankedResults (rank = 1-based position after filter)."""
    results: list[RankedResult] = []
    for i, hit in enumerate(hits):
        raw_doc_id = hit.payload.get("doc_id")
        if raw_doc_id is None or not isinstance(raw_doc_id, str):
            raise HybridRetrievalError(
                "missing or non-string doc_id in search result payload"
            )
        doc_id = str(raw_doc_id)
        if "\x00" in doc_id:
            raise HybridRetrievalError("doc_id in payload contains null bytes")
        if not doc_id.strip():
            raise HybridRetrievalError("doc_id in payload is blank or whitespace-only")
        results.append(
            ranked_result_from_position(
                result_id=hit.result_id,
                doc_id=doc_id,
                zero_based_position=i,
                raw_score=hit.score,
                payload=dict(hit.payload),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
__all__: list[str] = [
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
]
