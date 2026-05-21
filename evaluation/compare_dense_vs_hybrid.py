"""Paired dense-only versus hybrid retrieval comparator.

This module is intentionally evaluation-only. Unit tests use injected runners;
no Qdrant client, model runtime, server-side RRF, payloads, vectors, prompts,
or document text are required to produce the report artifacts.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html
import json
import math
import random
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol


SCHEMA_VERSION = "dense-vs-hybrid-summary-v1"
CSV_SCHEMA_VERSION = "dense-vs-hybrid-csv-v1"
REPORT_SCHEMA_VERSION = "dense-vs-hybrid-report-v1"
DEFAULT_RESULTS_DIR = Path("evaluation") / "results"
DEFAULT_ROWS_CSV = "dense_vs_hybrid_rows.csv"
DEFAULT_SUMMARY_JSON = "dense_vs_hybrid_summary.json"
DEFAULT_REPORT_MD = "dense_vs_hybrid_report.md"
DEFAULT_CHARTS_SVG = "dense_vs_hybrid_charts.svg"
DEFAULT_SEARCH_TOP_K = 20
DEFAULT_RETURN_TOP_K = 10
DEFAULT_BOOTSTRAP_RESAMPLES = 1000
DEFAULT_BOOTSTRAP_SEED = 42
DEFAULT_RRF_K = 60.0
DEFAULT_DENSE_WEIGHT = 1.0
DEFAULT_SPARSE_WEIGHT = 1.0
EPSILON = 1e-12

FORBIDDEN_OUTPUT_TOKENS = (
    "chunk_text",
    "prompt",
    "answer",
    "vector",
    "vectors",
    "dense_vector",
    "sparse_vector",
    "embedding",
    "embeddings",
)


class RetrievalMode(str, Enum):
    """Retrieval mode under comparison."""

    DENSE_ONLY = "dense_only"
    HYBRID = "hybrid"


class QueryCategory(str, Enum):
    """Coarse query category for breakdowns."""

    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID_Q = "hybrid"
    RISK = "risk"
    MACRO = "macro"
    ADVERSARIAL = "adversarial"
    MIXED = "mixed"


class Verdict(str, Enum):
    """Typed final decision for the comparator."""

    HYBRID_WINS = "hybrid_wins"
    DENSE_WINS = "dense_wins"
    NO_SIGNIFICANT_DIFFERENCE = "no_significant_difference"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class EvalQuery:
    """One benchmark query with qrels by document id."""

    query_id: str
    text: str
    category: QueryCategory
    qrels: Mapping[str, int]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        clean_query_id = _validate_text(self.query_id, "query_id")
        clean_text = _validate_text(self.text, "text")
        clean_category = _coerce_query_category(self.category)
        clean_qrels = _freeze_qrels(self.qrels)
        if clean_category is not QueryCategory.ADVERSARIAL and not clean_qrels:
            raise ValueError("non-adversarial queries must include qrels")
        clean_tags = tuple(_validate_text(tag, "tag") for tag in self.tags)

        object.__setattr__(self, "query_id", clean_query_id)
        object.__setattr__(self, "text", clean_text)
        object.__setattr__(self, "category", clean_category)
        object.__setattr__(self, "qrels", clean_qrels)
        object.__setattr__(self, "tags", clean_tags)


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    """Metadata describing one retrieval run."""

    run_id: str
    mode: RetrievalMode
    corpus_hash: str
    qdrant_snapshot_hash: str | None
    model: str
    timestamp_iso: str
    query_count: int
    k_values: tuple[int, ...]
    search_top_k: int
    return_top_k: int
    rrf_profile_name: str | None = None
    qdrant_server_version: str | None = None
    qdrant_client_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _validate_text(self.run_id, "run_id"))
        object.__setattr__(self, "mode", _coerce_retrieval_mode(self.mode))
        object.__setattr__(
            self,
            "corpus_hash",
            _validate_text(self.corpus_hash, "corpus_hash"),
        )
        if self.qdrant_snapshot_hash is not None:
            object.__setattr__(
                self,
                "qdrant_snapshot_hash",
                _validate_text(self.qdrant_snapshot_hash, "qdrant_snapshot_hash"),
            )
        object.__setattr__(self, "model", _validate_text(self.model, "model"))
        object.__setattr__(
            self,
            "timestamp_iso",
            _validate_text(self.timestamp_iso, "timestamp_iso"),
        )
        object.__setattr__(
            self,
            "query_count",
            _validate_non_negative_int(self.query_count, "query_count"),
        )
        if not self.k_values:
            raise ValueError("k_values cannot be empty")
        object.__setattr__(
            self,
            "k_values",
            tuple(_validate_positive_int(value, "k_values") for value in self.k_values),
        )
        object.__setattr__(
            self,
            "search_top_k",
            _validate_positive_int(self.search_top_k, "search_top_k"),
        )
        object.__setattr__(
            self,
            "return_top_k",
            _validate_positive_int(self.return_top_k, "return_top_k"),
        )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe run metadata."""

        return {
            "run_id": self.run_id,
            "mode": self.mode.value,
            "corpus_hash": self.corpus_hash,
            "qdrant_snapshot_hash": self.qdrant_snapshot_hash,
            "model": self.model,
            "timestamp_iso": self.timestamp_iso,
            "query_count": self.query_count,
            "k_values": list(self.k_values),
            "search_top_k": self.search_top_k,
            "return_top_k": self.return_top_k,
            "rrf_profile_name": self.rrf_profile_name,
            "qdrant_server_version": self.qdrant_server_version,
            "qdrant_client_version": self.qdrant_client_version,
        }


@dataclass(frozen=True, slots=True)
class PhaseLatencies:
    """Latency breakdown for a single query."""

    embed_dense_ms: float = 0.0
    embed_sparse_ms: float = 0.0
    search_dense_ms: float = 0.0
    search_sparse_ms: float = 0.0
    fusion_ms: float = 0.0
    total_ms: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "embed_dense_ms",
            "embed_sparse_ms",
            "search_dense_ms",
            "search_sparse_ms",
            "fusion_ms",
            "total_ms",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_float(getattr(self, field_name), field_name),
            )

    @property
    def overhead_ms(self) -> float:
        """Hybrid overhead components over a dense-only baseline."""

        return self.embed_sparse_ms + self.search_sparse_ms + self.fusion_ms

    def to_dict(self) -> dict[str, object]:
        return {
            "embed_dense_ms": self.embed_dense_ms,
            "embed_sparse_ms": self.embed_sparse_ms,
            "search_dense_ms": self.search_dense_ms,
            "search_sparse_ms": self.search_sparse_ms,
            "fusion_ms": self.fusion_ms,
            "total_ms": self.total_ms,
            "overhead_ms": self.overhead_ms,
        }


@dataclass(frozen=True, slots=True)
class RetrievalLikeResult:
    """Metadata-only retrieval result returned by injected runners."""

    hit_doc_ids: tuple[str, ...]
    hit_result_ids: tuple[str, ...]
    phase_latencies: PhaseLatencies
    retrieval_personality: str

    def __post_init__(self) -> None:
        clean_doc_ids = tuple(_validate_text(doc_id, "doc_id") for doc_id in self.hit_doc_ids)
        clean_result_ids = tuple(
            _validate_text(result_id, "result_id") for result_id in self.hit_result_ids
        )
        if len(clean_doc_ids) != len(clean_result_ids):
            raise ValueError("hit_doc_ids and hit_result_ids must have equal length")
        object.__setattr__(self, "hit_doc_ids", clean_doc_ids)
        object.__setattr__(self, "hit_result_ids", clean_result_ids)
        object.__setattr__(
            self,
            "retrieval_personality",
            _validate_text(self.retrieval_personality, "retrieval_personality"),
        )

    @property
    def rank_1_doc_id(self) -> str | None:
        return self.hit_doc_ids[0] if self.hit_doc_ids else None

    @property
    def latency_ms(self) -> float:
        return self.phase_latencies.total_ms


class RetrieverRunnerProtocol(Protocol):
    """Injected retrieval runner used by unit tests and future live adapters."""

    async def retrieve(self, query: EvalQuery) -> RetrievalLikeResult:
        """Retrieve metadata-only hits for one query."""
        ...


Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueryMetrics:
    """Metrics for one query and one retrieval mode."""

    query_id: str
    category: QueryCategory
    mode: RetrievalMode
    rank_1_doc_id: str | None
    hit_doc_ids: tuple[str, ...]
    hit_result_ids: tuple[str, ...]
    relevant_doc_ids: tuple[str, ...]
    precision_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_5: float
    latency_ms: float
    retrieval_personality: str
    phase_latencies: PhaseLatencies

    def to_dict(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "category": self.category.value,
            "mode": self.mode.value,
            "rank_1_doc_id": self.rank_1_doc_id,
            "hit_doc_ids": list(self.hit_doc_ids),
            "hit_result_ids": list(self.hit_result_ids),
            "relevant_doc_ids": list(self.relevant_doc_ids),
            "precision_at_5": self.precision_at_5,
            "recall_at_10": self.recall_at_10,
            "mrr": self.mrr,
            "ndcg_at_5": self.ndcg_at_5,
            "latency_ms": self.latency_ms,
            "retrieval_personality": self.retrieval_personality,
            "phase_latencies": self.phase_latencies.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class QueryComparisonRow:
    """Long-form CSV row: one query_id plus one mode."""

    schema_version: str
    run_id: str
    query_id: str
    query_category: str
    mode: str
    rank_1_doc_id: str
    precision_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_5: float
    latency_ms: float
    embed_dense_ms: float
    embed_sparse_ms: float
    search_dense_ms: float
    search_sparse_ms: float
    fusion_ms: float
    total_ms: float
    hit_doc_ids: tuple[str, ...]
    relevant_doc_ids: tuple[str, ...]
    retrieval_personality: str
    search_top_k: int
    return_top_k: int
    rrf_profile: str
    qdrant_server_version: str
    qdrant_client_version: str
    ef_search: str
    strict_mode: str


@dataclass(frozen=True, slots=True)
class HybridDecisionThresholds:
    """Thresholds used by the final promotion verdict."""

    min_recall10_abs_gain: float = 0.03
    min_ndcg5_abs_gain: float = 0.03
    max_latency_p95_multiplier: float = 2.5
    max_dense_win_rate: float = 0.25

    def __post_init__(self) -> None:
        for field_name in (
            "min_recall10_abs_gain",
            "min_ndcg5_abs_gain",
            "max_latency_p95_multiplier",
            "max_dense_win_rate",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_float(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "min_recall10_abs_gain": self.min_recall10_abs_gain,
            "min_ndcg5_abs_gain": self.min_ndcg5_abs_gain,
            "max_latency_p95_multiplier": self.max_latency_p95_multiplier,
            "max_dense_win_rate": self.max_dense_win_rate,
        }


@dataclass(frozen=True, slots=True)
class DeltaResult:
    """Aggregate delta for one metric."""

    metric: str
    dense_score: float
    hybrid_score: float
    absolute_delta: float
    relative_delta_pct: float
    dense_ci: tuple[float, float] | None
    hybrid_ci: tuple[float, float] | None
    ci_overlap: bool
    winner: str

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "dense_score": self.dense_score,
            "hybrid_score": self.hybrid_score,
            "absolute_delta": self.absolute_delta,
            "relative_delta_pct": self.relative_delta_pct,
            "dense_ci": None if self.dense_ci is None else list(self.dense_ci),
            "hybrid_ci": None if self.hybrid_ci is None else list(self.hybrid_ci),
            "ci_overlap": self.ci_overlap,
            "winner": self.winner,
        }


@dataclass(frozen=True, slots=True)
class ComparisonVerdict:
    """Final typed comparison verdict."""

    verdict: Verdict
    winning_mode: str | None
    metrics_hybrid_wins: tuple[str, ...]
    metrics_dense_wins: tuple[str, ...]
    ci_overlap_count: int
    promote_hybrid: bool
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "winning_mode": self.winning_mode,
            "metrics_hybrid_wins": list(self.metrics_hybrid_wins),
            "metrics_dense_wins": list(self.metrics_dense_wins),
            "ci_overlap_count": self.ci_overlap_count,
            "promote_hybrid": self.promote_hybrid,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class QdrantConfigSnapshot:
    """Optional metadata snapshot for live comparisons."""

    qdrant_server_version: str | None = None
    qdrant_client_version: str | None = None
    collection_name: str = ""
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "sparse"
    dense_distance: str | None = None
    dense_dimensions: int | None = None
    hnsw_m: int | None = None
    hnsw_ef_construct: int | None = None
    ef_search: int | None = None
    on_disk: bool | None = None
    quantization: str | None = None
    strict_mode: bool | None = None
    storage_engine: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "qdrant_server_version": self.qdrant_server_version,
            "qdrant_client_version": self.qdrant_client_version,
            "collection_name": self.collection_name,
            "dense_vector_name": self.dense_vector_name,
            "sparse_vector_name": self.sparse_vector_name,
            "dense_distance": self.dense_distance,
            "dense_dimensions": self.dense_dimensions,
            "hnsw_m": self.hnsw_m,
            "hnsw_ef_construct": self.hnsw_ef_construct,
            "ef_search": self.ef_search,
            "on_disk": self.on_disk,
            "quantization": self.quantization,
            "strict_mode": self.strict_mode,
            "storage_engine": self.storage_engine,
        }


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    """Executive dense-versus-hybrid comparison payload."""

    generated_at_iso: str
    dense_run: EvaluationRun
    hybrid_run: EvaluationRun
    qdrant_config_snapshot: QdrantConfigSnapshot
    aggregate_metrics_by_mode: Mapping[str, Mapping[str, float]]
    deltas: tuple[DeltaResult, ...]
    category_breakdown: Mapping[str, Mapping[str, float]]
    win_loss_tie: Mapping[str, int]
    latency_summary: Mapping[str, Mapping[str, float]]
    retrieval_personality_counts: Mapping[str, int]
    top_5_hybrid_gains: tuple[Mapping[str, object], ...]
    top_5_hybrid_regressions: tuple[Mapping[str, object], ...]
    verdict: ComparisonVerdict
    decision_thresholds: HybridDecisionThresholds

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at_iso": self.generated_at_iso,
            "dense_run": self.dense_run.to_dict(),
            "hybrid_run": self.hybrid_run.to_dict(),
            "qdrant_config_snapshot": self.qdrant_config_snapshot.to_dict(),
            "aggregate_metrics_by_mode": _nested_mapping_to_dict(
                self.aggregate_metrics_by_mode
            ),
            "deltas": [delta.to_dict() for delta in self.deltas],
            "category_breakdown": _nested_mapping_to_dict(self.category_breakdown),
            "win_loss_tie": dict(self.win_loss_tie),
            "latency_summary": _nested_mapping_to_dict(self.latency_summary),
            "retrieval_personality_counts": dict(self.retrieval_personality_counts),
            "top_5_hybrid_gains": [dict(row) for row in self.top_5_hybrid_gains],
            "top_5_hybrid_regressions": [
                dict(row) for row in self.top_5_hybrid_regressions
            ],
            "verdict": self.verdict.to_dict(),
            "decision_thresholds": self.decision_thresholds.to_dict(),
            "safety": {
                "includes_query_text": False,
                "includes_document_text": False,
                "includes_payload": False,
            },
        }


CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "mode",
    "query_id",
    "query_category",
    "rank_1_doc_id",
    "precision_at_5",
    "recall_at_10",
    "mrr",
    "ndcg_at_5",
    "latency_ms",
    "embed_dense_ms",
    "embed_sparse_ms",
    "search_dense_ms",
    "search_sparse_ms",
    "fusion_ms",
    "total_ms",
    "retrieval_personality",
    "hit_doc_ids",
    "relevant_doc_ids",
    "search_top_k",
    "return_top_k",
    "rrf_profile",
    "qdrant_server_version",
    "qdrant_client_version",
    "ef_search",
    "strict_mode",
)


def precision_at_k(
    hit_doc_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
) -> float:
    """Precision@k where relevance is qrels[doc_id] > 0."""

    clean_k = _validate_positive_int(k, "k")
    window = tuple(hit_doc_ids[:clean_k])
    if not window:
        return 0.0
    relevant_hits = sum(1 for doc_id in window if qrels.get(doc_id, 0) > 0)
    return relevant_hits / float(clean_k)


def recall_at_k(
    hit_doc_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
) -> float:
    """Recall@k where relevance is qrels[doc_id] > 0."""

    clean_k = _validate_positive_int(k, "k")
    relevant_docs = {doc_id for doc_id, grade in qrels.items() if grade > 0}
    if not relevant_docs:
        return 0.0
    found = {doc_id for doc_id in hit_doc_ids[:clean_k] if doc_id in relevant_docs}
    return len(found) / float(len(relevant_docs))


def reciprocal_rank(hit_doc_ids: Sequence[str], qrels: Mapping[str, int]) -> float:
    """Return reciprocal rank for the first relevant document."""

    for index, doc_id in enumerate(hit_doc_ids, start=1):
        if qrels.get(doc_id, 0) > 0:
            return 1.0 / float(index)
    return 0.0


def dcg_at_k(hit_doc_ids: Sequence[str], qrels: Mapping[str, int], k: int) -> float:
    """Discounted cumulative gain with gain = 2**rel - 1."""

    clean_k = _validate_positive_int(k, "k")
    total = 0.0
    for index, doc_id in enumerate(hit_doc_ids[:clean_k], start=1):
        rel = qrels.get(doc_id, 0)
        gain = (2.0**float(rel)) - 1.0
        total += gain / math.log2(float(index) + 1.0)
    return total


def ndcg_at_k(hit_doc_ids: Sequence[str], qrels: Mapping[str, int], k: int) -> float:
    """NDCG@k for graded relevance 0/1/2."""

    clean_k = _validate_positive_int(k, "k")
    ideal_doc_ids = tuple(
        doc_id
        for doc_id, _grade in sorted(qrels.items(), key=lambda item: item[1], reverse=True)
    )
    ideal = dcg_at_k(ideal_doc_ids, qrels, clean_k)
    if ideal <= 0.0:
        return 0.0
    return dcg_at_k(hit_doc_ids, qrels, clean_k) / ideal


def percentile_nearest_rank(values: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile, deterministic and dependency-free."""

    clean_values = _sorted_numeric_values(values)
    if not clean_values:
        return 0.0
    clean_percentile = _validate_percentile(percentile)
    rank = math.ceil((clean_percentile / 100.0) * len(clean_values))
    return clean_values[max(0, min(rank - 1, len(clean_values) - 1))]


def percentile_interpolated(values: Sequence[float], percentile: float) -> float:
    """Linearly interpolated percentile."""

    clean_values = _sorted_numeric_values(values)
    if not clean_values:
        return 0.0
    clean_percentile = _validate_percentile(percentile)
    if len(clean_values) == 1:
        return clean_values[0]
    position = (len(clean_values) - 1) * (clean_percentile / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean_values[int(position)]
    weight = position - lower
    return clean_values[lower] * (1.0 - weight) + clean_values[upper] * weight


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    confidence: float = 0.95,
    rng_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Bootstrap confidence interval for the mean using random.Random(seed)."""

    clean_values = _sorted_numeric_values(values)
    if not clean_values:
        return (0.0, 0.0)
    clean_resamples = _validate_positive_int(n_resamples, "n_resamples")
    clean_confidence = _validate_confidence(confidence)
    rng = random.Random(rng_seed)
    means: list[float] = []
    sample_size = len(clean_values)
    for _ in range(clean_resamples):
        sample = [clean_values[rng.randrange(sample_size)] for _index in range(sample_size)]
        means.append(_mean(sample))
    alpha = (1.0 - clean_confidence) / 2.0
    return (
        percentile_interpolated(means, alpha * 100.0),
        percentile_interpolated(means, (1.0 - alpha) * 100.0),
    )


def delta_pair(
    dense: float,
    hybrid: float,
    *,
    metric: str = "metric",
    dense_ci: tuple[float, float] | None = None,
    hybrid_ci: tuple[float, float] | None = None,
) -> DeltaResult:
    """Return absolute and relative hybrid-minus-dense delta."""

    dense_score = _validate_finite_float(dense, "dense")
    hybrid_score = _validate_finite_float(hybrid, "hybrid")
    absolute_delta = hybrid_score - dense_score
    relative_delta_pct = 0.0
    if abs(dense_score) > EPSILON:
        relative_delta_pct = (absolute_delta / abs(dense_score)) * 100.0
    overlap = _ci_overlap(dense_ci, hybrid_ci)
    winner = "tie"
    if absolute_delta > EPSILON:
        winner = RetrievalMode.HYBRID.value
    elif absolute_delta < -EPSILON:
        winner = RetrievalMode.DENSE_ONLY.value
    return DeltaResult(
        metric=metric,
        dense_score=dense_score,
        hybrid_score=hybrid_score,
        absolute_delta=absolute_delta,
        relative_delta_pct=relative_delta_pct,
        dense_ci=dense_ci,
        hybrid_ci=hybrid_ci,
        ci_overlap=overlap,
        winner=winner,
    )


def classify_retrieval_effect(result: object) -> str:
    """Classify how dense and sparse ranks affected a fused result."""

    dense_rank = getattr(result, "dense_rank", None)
    sparse_rank = getattr(result, "sparse_rank", None)
    if dense_rank is None and sparse_rank is not None:
        return "sparse_only_rescue"
    if sparse_rank is None and dense_rank is not None:
        return "dense_only_rescue"
    if isinstance(dense_rank, int) and isinstance(sparse_rank, int):
        if sparse_rank < dense_rank:
            return "lexical_boost"
        if dense_rank < sparse_rank:
            return "semantic_boost"
        return "agreement"
    return "unknown"


async def run_mode(
    *,
    mode: RetrievalMode,
    queries: Sequence[EvalQuery],
    runner: RetrieverRunnerProtocol,
    run: EvaluationRun,
    cooldown_ms: float,
    sleeper: Sleeper = asyncio.sleep,
) -> list[QueryMetrics]:
    """Run all queries for one mode and compute per-query metrics."""

    clean_mode = _coerce_retrieval_mode(mode)
    if run.mode is not clean_mode:
        raise ValueError("run.mode must match mode")
    clean_cooldown = _validate_non_negative_float(cooldown_ms, "cooldown_ms")
    results: list[QueryMetrics] = []
    for index, query in enumerate(queries):
        retrieval = await runner.retrieve(query)
        results.append(_metrics_from_retrieval(query=query, mode=clean_mode, result=retrieval))
        if clean_cooldown > 0.0 and index < len(queries) - 1:
            await sleeper(clean_cooldown / 1000.0)
    return results


def assert_paired_query_metrics(
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
) -> None:
    """Require identical query_id coverage for paired comparison."""

    dense_ids = tuple(sorted(_metrics_by_query_id(dense_metrics)))
    hybrid_ids = tuple(sorted(_metrics_by_query_id(hybrid_metrics)))
    if dense_ids != hybrid_ids:
        raise ValueError("dense and hybrid metrics must have identical query_id coverage")


def assert_runs_comparable(dense_run: EvaluationRun, hybrid_run: EvaluationRun) -> None:
    """Abort comparison if runs do not share corpus, model and retrieval config."""

    if dense_run.corpus_hash != hybrid_run.corpus_hash:
        raise ValueError("runs must use identical corpus_hash")
    if dense_run.model != hybrid_run.model:
        raise ValueError("runs must use identical model")
    if dense_run.k_values != hybrid_run.k_values:
        raise ValueError("runs must use identical k_values")
    if dense_run.search_top_k != hybrid_run.search_top_k:
        raise ValueError("runs must use identical search_top_k")
    if dense_run.return_top_k != hybrid_run.return_top_k:
        raise ValueError("runs must use identical return_top_k")
    if dense_run.query_count != hybrid_run.query_count:
        raise ValueError("runs must use identical query_count")


def compute_corpus_hash(queries: Sequence[EvalQuery]) -> str:
    """Stable hash of benchmark inputs, including text and qrels."""

    payload = [
        {
            "query_id": query.query_id,
            "text": query.text,
            "category": query.category.value,
            "qrels": dict(sorted(query.qrels.items())),
            "tags": list(query.tags),
        }
        for query in queries
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def make_run_id(corpus_hash: str, mode: RetrievalMode, timestamp_iso: str) -> str:
    """Deterministic run id for fixed inputs."""

    clean_hash = _validate_text(corpus_hash, "corpus_hash")
    clean_mode = _coerce_retrieval_mode(mode)
    clean_timestamp = _validate_text(timestamp_iso, "timestamp_iso")
    payload = f"{clean_hash}:{clean_mode.value}:{clean_timestamp}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def build_evaluation_run(
    *,
    mode: RetrievalMode,
    queries: Sequence[EvalQuery],
    model: str,
    timestamp_iso: str,
    search_top_k: int,
    return_top_k: int,
    rrf_profile_name: str | None,
    k_values: Sequence[int] = (5, 10),
    qdrant_snapshot_hash: str | None = None,
    qdrant_server_version: str | None = None,
    qdrant_client_version: str | None = None,
) -> EvaluationRun:
    """Build validated run metadata for one mode."""

    corpus_hash = compute_corpus_hash(queries)
    clean_mode = _coerce_retrieval_mode(mode)
    return EvaluationRun(
        run_id=make_run_id(corpus_hash, clean_mode, timestamp_iso),
        mode=clean_mode,
        corpus_hash=corpus_hash,
        qdrant_snapshot_hash=qdrant_snapshot_hash,
        model=model,
        timestamp_iso=timestamp_iso,
        query_count=len(queries),
        k_values=tuple(k_values),
        search_top_k=search_top_k,
        return_top_k=return_top_k,
        rrf_profile_name=rrf_profile_name,
        qdrant_server_version=qdrant_server_version,
        qdrant_client_version=qdrant_client_version,
    )


def build_query_rows(
    *,
    run: EvaluationRun,
    metrics: Sequence[QueryMetrics],
    qdrant_snapshot: QdrantConfigSnapshot,
) -> list[QueryComparisonRow]:
    """Convert query metrics to long-form CSV rows."""

    rows: list[QueryComparisonRow] = []
    for metric in metrics:
        rows.append(
            QueryComparisonRow(
                schema_version=CSV_SCHEMA_VERSION,
                run_id=run.run_id,
                query_id=metric.query_id,
                query_category=metric.category.value,
                mode=metric.mode.value,
                rank_1_doc_id="" if metric.rank_1_doc_id is None else metric.rank_1_doc_id,
                precision_at_5=metric.precision_at_5,
                recall_at_10=metric.recall_at_10,
                mrr=metric.mrr,
                ndcg_at_5=metric.ndcg_at_5,
                latency_ms=metric.latency_ms,
                embed_dense_ms=metric.phase_latencies.embed_dense_ms,
                embed_sparse_ms=metric.phase_latencies.embed_sparse_ms,
                search_dense_ms=metric.phase_latencies.search_dense_ms,
                search_sparse_ms=metric.phase_latencies.search_sparse_ms,
                fusion_ms=metric.phase_latencies.fusion_ms,
                total_ms=metric.phase_latencies.total_ms,
                hit_doc_ids=metric.hit_doc_ids,
                relevant_doc_ids=metric.relevant_doc_ids,
                retrieval_personality=metric.retrieval_personality,
                search_top_k=run.search_top_k,
                return_top_k=run.return_top_k,
                rrf_profile="" if run.rrf_profile_name is None else run.rrf_profile_name,
                qdrant_server_version=qdrant_snapshot.qdrant_server_version or "",
                qdrant_client_version=qdrant_snapshot.qdrant_client_version or "",
                ef_search="" if qdrant_snapshot.ef_search is None else str(qdrant_snapshot.ef_search),
                strict_mode=""
                if qdrant_snapshot.strict_mode is None
                else str(qdrant_snapshot.strict_mode).lower(),
            )
        )
    return rows


def build_summary(
    *,
    dense_run: EvaluationRun,
    hybrid_run: EvaluationRun,
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
    qdrant_snapshot: QdrantConfigSnapshot,
    thresholds: HybridDecisionThresholds | None = None,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    generated_at_iso: str | None = None,
) -> ComparisonSummary:
    """Build the executive comparison summary."""

    active_thresholds = thresholds or HybridDecisionThresholds()
    assert_runs_comparable(dense_run, hybrid_run)
    assert_paired_query_metrics(dense_metrics, hybrid_metrics)
    generated_at = generated_at_iso or datetime.now(UTC).replace(microsecond=0).isoformat()
    aggregate = {
        RetrievalMode.DENSE_ONLY.value: aggregate_metrics(dense_metrics),
        RetrievalMode.HYBRID.value: aggregate_metrics(hybrid_metrics),
    }
    deltas = _build_deltas(
        dense_metrics=dense_metrics,
        hybrid_metrics=hybrid_metrics,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    wins = _win_loss_tie(dense_metrics, hybrid_metrics)
    latency = {
        RetrievalMode.DENSE_ONLY.value: latency_summary(dense_metrics),
        RetrievalMode.HYBRID.value: latency_summary(hybrid_metrics),
    }
    category = category_breakdown(dense_metrics, hybrid_metrics)
    personality = retrieval_personality_counts(hybrid_metrics)
    top_gains, top_regressions = top_query_deltas(dense_metrics, hybrid_metrics)
    verdict = decide_hybrid_promotion_from_parts(
        deltas=deltas,
        win_loss_tie=wins,
        latency_summary_by_mode=latency,
        thresholds=active_thresholds,
        query_count=len(dense_metrics),
    )
    return ComparisonSummary(
        generated_at_iso=generated_at,
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        qdrant_config_snapshot=qdrant_snapshot,
        aggregate_metrics_by_mode=aggregate,
        deltas=deltas,
        category_breakdown=category,
        win_loss_tie=wins,
        latency_summary=latency,
        retrieval_personality_counts=personality,
        top_5_hybrid_gains=top_gains,
        top_5_hybrid_regressions=top_regressions,
        verdict=verdict,
        decision_thresholds=active_thresholds,
    )


def aggregate_metrics(metrics: Sequence[QueryMetrics]) -> dict[str, float]:
    """Mean quality metrics for one mode."""

    return {
        "precision_at_5": _mean([metric.precision_at_5 for metric in metrics]),
        "recall_at_10": _mean([metric.recall_at_10 for metric in metrics]),
        "mrr": _mean([metric.mrr for metric in metrics]),
        "ndcg_at_5": _mean([metric.ndcg_at_5 for metric in metrics]),
        "latency_ms_mean": _mean([metric.latency_ms for metric in metrics]),
    }


def latency_summary(metrics: Sequence[QueryMetrics]) -> dict[str, float]:
    """Latency p50/p95/mean for one mode."""

    values = [metric.latency_ms for metric in metrics]
    return {
        "p50_ms": percentile_interpolated(values, 50.0),
        "p95_ms": percentile_interpolated(values, 95.0),
        "mean_ms": _mean(values),
    }


def category_breakdown(
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
) -> dict[str, dict[str, float]]:
    """Aggregate recall/NDCG deltas by query category."""

    assert_paired_query_metrics(dense_metrics, hybrid_metrics)
    hybrid_by_query_id = _metrics_by_query_id(hybrid_metrics)
    grouped: dict[str, list[tuple[QueryMetrics, QueryMetrics]]] = {}
    for dense in dense_metrics:
        hybrid = hybrid_by_query_id[dense.query_id]
        grouped.setdefault(dense.category.value, []).append((dense, hybrid))
    breakdown: dict[str, dict[str, float]] = {}
    for category, pairs in sorted(grouped.items()):
        recall_deltas = [hybrid.recall_at_10 - dense.recall_at_10 for dense, hybrid in pairs]
        ndcg_deltas = [hybrid.ndcg_at_5 - dense.ndcg_at_5 for dense, hybrid in pairs]
        wins = sum(1 for dense, hybrid in pairs if hybrid.ndcg_at_5 > dense.ndcg_at_5)
        losses = sum(1 for dense, hybrid in pairs if hybrid.ndcg_at_5 < dense.ndcg_at_5)
        ties = len(pairs) - wins - losses
        breakdown[category] = {
            "query_count": float(len(pairs)),
            "delta_recall_at_10": _mean(recall_deltas),
            "delta_ndcg_at_5": _mean(ndcg_deltas),
            "wins": float(wins),
            "losses": float(losses),
            "ties": float(ties),
        }
    return breakdown


def retrieval_personality_counts(metrics: Sequence[QueryMetrics]) -> dict[str, int]:
    """Count retrieval personalities in one mode."""

    counter = Counter(metric.retrieval_personality for metric in metrics)
    return dict(sorted(counter.items()))


def top_query_deltas(
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    """Return top hybrid gains and regressions by NDCG@5 delta."""

    assert_paired_query_metrics(dense_metrics, hybrid_metrics)
    hybrid_by_query_id = _metrics_by_query_id(hybrid_metrics)
    rows: list[dict[str, object]] = []
    for dense in dense_metrics:
        hybrid = hybrid_by_query_id[dense.query_id]
        rows.append(
            {
                "query_id": dense.query_id,
                "category": dense.category.value,
                "delta_ndcg_at_5": hybrid.ndcg_at_5 - dense.ndcg_at_5,
                "delta_recall_at_10": hybrid.recall_at_10 - dense.recall_at_10,
                "dense_rank_1_doc_id": dense.rank_1_doc_id,
                "hybrid_rank_1_doc_id": hybrid.rank_1_doc_id,
            }
        )
    gains = tuple(sorted(rows, key=lambda row: _row_float(row, "delta_ndcg_at_5"), reverse=True)[:5])
    regressions = tuple(sorted(rows, key=lambda row: _row_float(row, "delta_ndcg_at_5"))[:5])
    return gains, regressions


def decide_hybrid_promotion(summary: ComparisonSummary) -> ComparisonVerdict:
    """Return the already computed verdict from a summary."""

    return summary.verdict


def decide_hybrid_promotion_from_parts(
    *,
    deltas: Sequence[DeltaResult],
    win_loss_tie: Mapping[str, int],
    latency_summary_by_mode: Mapping[str, Mapping[str, float]],
    thresholds: HybridDecisionThresholds,
    query_count: int,
) -> ComparisonVerdict:
    """Apply promotion thresholds to aggregate deltas and latency."""

    delta_by_metric = {delta.metric: delta for delta in deltas}
    recall_delta = delta_by_metric["recall_at_10"].absolute_delta
    ndcg_delta = delta_by_metric["ndcg_at_5"].absolute_delta
    dense_wins = win_loss_tie.get("dense_wins", 0)
    dense_win_rate = 0.0 if query_count == 0 else dense_wins / float(query_count)
    dense_p95 = latency_summary_by_mode[RetrievalMode.DENSE_ONLY.value]["p95_ms"]
    hybrid_p95 = latency_summary_by_mode[RetrievalMode.HYBRID.value]["p95_ms"]
    latency_multiplier = _safe_ratio(hybrid_p95, dense_p95)
    quality_deltas = [
        delta for delta in deltas if delta.metric in {"precision_at_5", "recall_at_10", "mrr", "ndcg_at_5"}
    ]
    hybrid_wins = tuple(delta.metric for delta in quality_deltas if delta.absolute_delta > EPSILON)
    dense_metric_wins = tuple(
        delta.metric for delta in quality_deltas if delta.absolute_delta < -EPSILON
    )
    ci_overlap_count = sum(1 for delta in quality_deltas if delta.ci_overlap)

    if (
        recall_delta >= thresholds.min_recall10_abs_gain
        and ndcg_delta >= thresholds.min_ndcg5_abs_gain
        and latency_multiplier <= thresholds.max_latency_p95_multiplier
        and dense_win_rate <= thresholds.max_dense_win_rate
    ):
        return ComparisonVerdict(
            verdict=Verdict.HYBRID_WINS,
            winning_mode=RetrievalMode.HYBRID.value,
            metrics_hybrid_wins=hybrid_wins,
            metrics_dense_wins=dense_metric_wins,
            ci_overlap_count=ci_overlap_count,
            promote_hybrid=True,
            note="hybrid quality gain clears thresholds with acceptable latency overhead",
        )

    if recall_delta < -thresholds.min_recall10_abs_gain or ndcg_delta < -thresholds.min_ndcg5_abs_gain:
        return ComparisonVerdict(
            verdict=Verdict.DENSE_WINS,
            winning_mode=RetrievalMode.DENSE_ONLY.value,
            metrics_hybrid_wins=hybrid_wins,
            metrics_dense_wins=dense_metric_wins,
            ci_overlap_count=ci_overlap_count,
            promote_hybrid=False,
            note="hybrid regresses key quality metrics",
        )

    if ci_overlap_count == len(quality_deltas):
        return ComparisonVerdict(
            verdict=Verdict.INCONCLUSIVE,
            winning_mode=None,
            metrics_hybrid_wins=hybrid_wins,
            metrics_dense_wins=dense_metric_wins,
            ci_overlap_count=ci_overlap_count,
            promote_hybrid=False,
            note="confidence intervals overlap across quality metrics",
        )

    return ComparisonVerdict(
        verdict=Verdict.NO_SIGNIFICANT_DIFFERENCE,
        winning_mode=None,
        metrics_hybrid_wins=hybrid_wins,
        metrics_dense_wins=dense_metric_wins,
        ci_overlap_count=ci_overlap_count,
        promote_hybrid=False,
        note="quality deltas do not clear promotion thresholds",
    )


def write_csv(rows: Sequence[QueryComparisonRow], path: Path) -> None:
    """Write long-form CSV rows without query text or payloads."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in rows:
            csv_row = _row_to_csv_dict(row)
            _assert_safe_text("|".join(csv_row.values()))
            writer.writerow(csv_row)


def write_json(summary: ComparisonSummary, path: Path) -> None:
    """Write executive JSON summary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary.to_dict()
    _assert_safe_serialized_payload(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown(summary: ComparisonSummary, path: Path) -> None:
    """Write human-readable Markdown report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown_report(summary)
    _assert_safe_text(markdown)
    path.write_text(markdown, encoding="utf-8")


def write_svg(summary: ComparisonSummary, path: Path) -> None:
    """Write dependency-free SVG dashboard."""

    path.parent.mkdir(parents=True, exist_ok=True)
    svg = render_svg_dashboard(summary)
    _assert_safe_text(svg)
    path.write_text(svg, encoding="utf-8")


def render_markdown_report(summary: ComparisonSummary) -> str:
    """Render a concise Markdown report without query or document text."""

    dense = summary.aggregate_metrics_by_mode[RetrievalMode.DENSE_ONLY.value]
    hybrid = summary.aggregate_metrics_by_mode[RetrievalMode.HYBRID.value]
    lines = [
        f"# Dense vs Hybrid Report ({REPORT_SCHEMA_VERSION})",
        "",
        "## Executive Summary",
        "",
        f"- Verdict: `{summary.verdict.verdict.value}`",
        f"- Promote hybrid: `{str(summary.verdict.promote_hybrid).lower()}`",
        f"- Note: {summary.verdict.note}",
        "",
        "## Metrics",
        "",
        "| Metric | Dense | Hybrid | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in ("precision_at_5", "recall_at_10", "mrr", "ndcg_at_5"):
        delta = hybrid[metric] - dense[metric]
        lines.append(
            f"| {metric} | {_fmt_float(dense[metric])} | {_fmt_float(hybrid[metric])} | {_fmt_signed(delta)} |"
        )
    lines.extend(
        [
            "",
            "## Latency",
            "",
            "| Mode | p50 ms | p95 ms | mean ms |",
            "|---|---:|---:|---:|",
        ]
    )
    for mode, values in summary.latency_summary.items():
        lines.append(
            f"| {mode} | {_fmt_float(values['p50_ms'])} | {_fmt_float(values['p95_ms'])} | {_fmt_float(values['mean_ms'])} |"
        )
    lines.extend(
        [
            "",
            "## Top Hybrid Gains",
            "",
            "| query_id | category | delta_ndcg_at_5 |",
            "|---|---|---:|",
        ]
    )
    for row in summary.top_5_hybrid_gains:
        lines.append(
            f"| {row['query_id']} | {row['category']} | {_fmt_signed(_row_float(row, 'delta_ndcg_at_5'))} |"
        )
    lines.extend(
        [
            "",
            "## Top Hybrid Regressions",
            "",
            "| query_id | category | delta_ndcg_at_5 |",
            "|---|---|---:|",
        ]
    )
    for row in summary.top_5_hybrid_regressions:
        lines.append(
            f"| {row['query_id']} | {row['category']} | {_fmt_signed(_row_float(row, 'delta_ndcg_at_5'))} |"
        )
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "Run the comparator with the same query manifest, collection, top-k values and RRF profile.",
            "",
            "## Limitations",
            "",
            "- This report compares retrieval metadata, not generated responses.",
            "- Query text and document text are intentionally omitted by default.",
            "",
        ]
    )
    return "\n".join(lines)


def render_svg_dashboard(summary: ComparisonSummary) -> str:
    """Render a static SVG dashboard using only stdlib string generation."""

    dense = summary.aggregate_metrics_by_mode[RetrievalMode.DENSE_ONLY.value]
    hybrid = summary.aggregate_metrics_by_mode[RetrievalMode.HYBRID.value]
    metrics = ("precision_at_5", "recall_at_10", "mrr", "ndcg_at_5")
    latency_dense = summary.latency_summary[RetrievalMode.DENSE_ONLY.value]
    latency_hybrid = summary.latency_summary[RetrievalMode.HYBRID.value]
    width = 1100
    height = 980
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Arial,sans-serif;font-size:13px}.title{font-size:20px;font-weight:bold}.small{font-size:11px}.dense{fill:#2F80ED}.hybrid{fill:#27AE60}.neg{fill:#C0392B}.pos{fill:#27AE60}.axis{stroke:#333;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}</style>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="30" y="35" class="title">Dense vs Hybrid Visual Report</text>',
        _svg_quality_chart(dense, hybrid, metrics, x=30, y=70),
        _svg_latency_chart(latency_dense, latency_hybrid, x=620, y=70),
        _svg_delta_waterfall(summary.top_5_hybrid_gains, summary.top_5_hybrid_regressions, x=30, y=350),
        _svg_category_table(summary.category_breakdown, x=620, y=350),
        _svg_personality_bar(summary.retrieval_personality_counts, x=30, y=720),
        _svg_quality_vs_delta_scatter(summary.top_5_hybrid_gains, summary.top_5_hybrid_regressions, x=620, y=720),
        "</svg>",
    ]
    return "\n".join(parts)


def format_terminal_summary(summary: ComparisonSummary) -> str:
    """Return a compact terminal summary with ASCII bars."""

    dense = summary.aggregate_metrics_by_mode[RetrievalMode.DENSE_ONLY.value]
    hybrid = summary.aggregate_metrics_by_mode[RetrievalMode.HYBRID.value]
    lines = [
        "Dense vs Hybrid Comparator",
        f"Verdict: {summary.verdict.verdict.value} | promote_hybrid={summary.verdict.promote_hybrid}",
        "",
        "Metric           Dense     Hybrid    Delta     Bar",
    ]
    for metric in ("precision_at_5", "recall_at_10", "mrr", "ndcg_at_5"):
        delta = hybrid[metric] - dense[metric]
        lines.append(
            f"{metric:<16} {_fmt_float(dense[metric]):>7} {_fmt_float(hybrid[metric]):>9} {_fmt_signed(delta):>8}  {_ascii_bar(delta)}"
        )
    dense_p95 = summary.latency_summary[RetrievalMode.DENSE_ONLY.value]["p95_ms"]
    hybrid_p95 = summary.latency_summary[RetrievalMode.HYBRID.value]["p95_ms"]
    lines.extend(
        [
            "",
            f"Latency p95 ms   dense={_fmt_float(dense_p95)} hybrid={_fmt_float(hybrid_p95)} multiplier={_fmt_float(_safe_ratio(hybrid_p95, dense_p95))}",
            "Top gains: " + ", ".join(str(row["query_id"]) for row in summary.top_5_hybrid_gains[:5]),
            "Top regressions: "
            + ", ".join(str(row["query_id"]) for row in summary.top_5_hybrid_regressions[:5]),
        ]
    )
    return "\n".join(lines) + "\n"


def write_all_outputs(
    *,
    rows: Sequence[QueryComparisonRow],
    summary: ComparisonSummary,
    output_dir: Path,
) -> dict[str, Path]:
    """Write CSV, JSON, Markdown and SVG artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_dir / DEFAULT_ROWS_CSV,
        "json": output_dir / DEFAULT_SUMMARY_JSON,
        "markdown": output_dir / DEFAULT_REPORT_MD,
        "svg": output_dir / DEFAULT_CHARTS_SVG,
    }
    write_csv(rows, paths["csv"])
    write_json(summary, paths["json"])
    write_markdown(summary, paths["markdown"])
    write_svg(summary, paths["svg"])
    return paths


def load_eval_queries(path: Path | None) -> tuple[EvalQuery, ...]:
    """Load a JSON query manifest or return the built-in synthetic manifest."""

    if path is None:
        return default_eval_queries()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("query manifest must be an object")
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("query manifest must contain a queries list")
    queries: list[EvalQuery] = []
    for raw in raw_queries:
        if not isinstance(raw, dict):
            raise ValueError("each query must be an object")
        raw_qrels = raw.get("qrels", {})
        if not isinstance(raw_qrels, dict):
            raise ValueError("qrels must be an object")
        raw_tags = raw.get("tags", ())
        if not isinstance(raw_tags, list):
            raise ValueError("tags must be a list")
        queries.append(
            EvalQuery(
                query_id=_require_str(raw.get("query_id"), "query_id"),
                text=_require_str(raw.get("text"), "text"),
                category=QueryCategory(_require_str(raw.get("category"), "category")),
                qrels={_require_str(key, "qrel doc_id"): _require_int(value, "qrel grade") for key, value in raw_qrels.items()},
                tags=tuple(_require_str(tag, "tag") for tag in raw_tags),
            )
        )
    return tuple(queries)


def default_eval_queries() -> tuple[EvalQuery, ...]:
    """Small synthetic financial benchmark for dry-run reports."""

    return (
        EvalQuery(
            query_id="q_fii_01",
            text="MXRF11 dividend yield FII de papel CRI high grade",
            category=QueryCategory.LEXICAL,
            qrels={"smoke-fii-mxrf11": 2, "smoke-tesouro-selic": 0},
            tags=("ticker", "fii", "cri"),
        ),
        EvalQuery(
            query_id="q_selic_01",
            text="reserva de emergencia liquidez diaria baixo risco CDI",
            category=QueryCategory.MACRO,
            qrels={"smoke-tesouro-selic": 2, "smoke-fii-mxrf11": 0},
            tags=("selic", "reserva"),
        ),
        EvalQuery(
            query_id="q_duration_01",
            text="marcacao a mercado duration longa alta de juros",
            category=QueryCategory.RISK,
            qrels={"smoke-marcacao-prefixado-ipca": 2, "smoke-tesouro-selic": 1},
            tags=("duration", "juros"),
        ),
    )


@dataclass(frozen=True, slots=True)
class StaticRetrieverRunner:
    """Deterministic metadata-only runner used for dry-run demos and tests."""

    results_by_query_id: Mapping[str, RetrievalLikeResult]

    async def retrieve(self, query: EvalQuery) -> RetrievalLikeResult:
        result = self.results_by_query_id.get(query.query_id)
        if result is None:
            return RetrievalLikeResult(
                hit_doc_ids=(),
                hit_result_ids=(),
                phase_latencies=PhaseLatencies(total_ms=1.0),
                retrieval_personality="empty",
            )
        return result


def default_static_runners() -> tuple[StaticRetrieverRunner, StaticRetrieverRunner]:
    """Return deterministic dry-run dense and hybrid runners."""

    dense = StaticRetrieverRunner(
        {
            "q_fii_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-tesouro-selic", "smoke-marcacao-prefixado-ipca"),
                hit_result_ids=("selic-1", "duration-1"),
                phase_latencies=PhaseLatencies(embed_dense_ms=4.0, search_dense_ms=5.0, total_ms=9.0),
                retrieval_personality="dense_only_baseline",
            ),
            "q_selic_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-tesouro-selic", "smoke-fii-mxrf11"),
                hit_result_ids=("selic-1", "fii-1"),
                phase_latencies=PhaseLatencies(embed_dense_ms=4.0, search_dense_ms=6.0, total_ms=10.0),
                retrieval_personality="dense_only_baseline",
            ),
            "q_duration_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-fii-mxrf11", "smoke-tesouro-selic"),
                hit_result_ids=("fii-1", "selic-1"),
                phase_latencies=PhaseLatencies(embed_dense_ms=4.0, search_dense_ms=5.0, total_ms=9.0),
                retrieval_personality="dense_only_baseline",
            ),
        }
    )
    hybrid = StaticRetrieverRunner(
        {
            "q_fii_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-fii-mxrf11", "smoke-tesouro-selic"),
                hit_result_ids=("fii-1", "selic-1"),
                phase_latencies=PhaseLatencies(
                    embed_dense_ms=4.0,
                    embed_sparse_ms=2.0,
                    search_dense_ms=5.0,
                    search_sparse_ms=3.0,
                    fusion_ms=1.0,
                    total_ms=15.0,
                ),
                retrieval_personality="lexical_boost",
            ),
            "q_selic_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-tesouro-selic", "smoke-fii-mxrf11"),
                hit_result_ids=("selic-1", "fii-1"),
                phase_latencies=PhaseLatencies(
                    embed_dense_ms=4.0,
                    embed_sparse_ms=2.0,
                    search_dense_ms=5.0,
                    search_sparse_ms=3.0,
                    fusion_ms=1.0,
                    total_ms=15.0,
                ),
                retrieval_personality="agreement",
            ),
            "q_duration_01": RetrievalLikeResult(
                hit_doc_ids=("smoke-marcacao-prefixado-ipca", "smoke-tesouro-selic"),
                hit_result_ids=("duration-1", "selic-1"),
                phase_latencies=PhaseLatencies(
                    embed_dense_ms=4.0,
                    embed_sparse_ms=2.0,
                    search_dense_ms=5.0,
                    search_sparse_ms=3.0,
                    fusion_ms=1.0,
                    total_ms=15.0,
                ),
                retrieval_personality="sparse_only_rescue",
            ),
        }
    )
    return dense, hybrid


async def compare_dense_vs_hybrid(
    *,
    queries: Sequence[EvalQuery],
    dense_runner: RetrieverRunnerProtocol,
    hybrid_runner: RetrieverRunnerProtocol,
    collection_name: str,
    search_top_k: int = DEFAULT_SEARCH_TOP_K,
    return_top_k: int = DEFAULT_RETURN_TOP_K,
    cooldown_ms: float = 0.0,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    timestamp_iso: str | None = None,
    model: str = "local-rag",
    qdrant_snapshot: QdrantConfigSnapshot | None = None,
    sleeper: Sleeper = asyncio.sleep,
) -> tuple[list[QueryComparisonRow], ComparisonSummary]:
    """Run paired dense and hybrid retrieval and build report payloads."""

    clean_collection = _validate_text(collection_name, "collection_name")
    clean_timestamp = timestamp_iso or datetime.now(UTC).replace(microsecond=0).isoformat()
    query_tuple = tuple(queries)
    dense_run = build_evaluation_run(
        mode=RetrievalMode.DENSE_ONLY,
        queries=query_tuple,
        model=model,
        timestamp_iso=clean_timestamp,
        search_top_k=search_top_k,
        return_top_k=return_top_k,
        rrf_profile_name=None,
    )
    hybrid_run = build_evaluation_run(
        mode=RetrievalMode.HYBRID,
        queries=query_tuple,
        model=model,
        timestamp_iso=clean_timestamp,
        search_top_k=search_top_k,
        return_top_k=return_top_k,
        rrf_profile_name="default",
    )
    dense_metrics = await run_mode(
        mode=RetrievalMode.DENSE_ONLY,
        queries=query_tuple,
        runner=dense_runner,
        run=dense_run,
        cooldown_ms=cooldown_ms,
        sleeper=sleeper,
    )
    hybrid_metrics = await run_mode(
        mode=RetrievalMode.HYBRID,
        queries=query_tuple,
        runner=hybrid_runner,
        run=hybrid_run,
        cooldown_ms=cooldown_ms,
        sleeper=sleeper,
    )
    snapshot = qdrant_snapshot or QdrantConfigSnapshot(collection_name=clean_collection)
    summary = build_summary(
        dense_run=dense_run,
        hybrid_run=hybrid_run,
        dense_metrics=dense_metrics,
        hybrid_metrics=hybrid_metrics,
        qdrant_snapshot=snapshot,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
        generated_at_iso=clean_timestamp,
    )
    rows = [
        *build_query_rows(run=dense_run, metrics=dense_metrics, qdrant_snapshot=snapshot),
        *build_query_rows(run=hybrid_run, metrics=hybrid_metrics, qdrant_snapshot=snapshot),
    ]
    return rows, summary


async def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for the offline-safe comparator."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if bool(args.include_debug_text):
        sys.stderr.write("debug text output is not supported by PR-11 default artifacts\n")
        return 2
    if bool(args.run_live):
        sys.stderr.write("live mode is not wired in PR-11; use injected runners in integration code\n")
        return 2

    queries = load_eval_queries(None if args.queries is None else Path(args.queries))
    dense_runner, hybrid_runner = default_static_runners()
    rows, summary = await compare_dense_vs_hybrid(
        queries=queries,
        dense_runner=dense_runner,
        hybrid_runner=hybrid_runner,
        collection_name=str(args.collection),
        search_top_k=int(args.search_top_k),
        return_top_k=int(args.return_top_k),
        cooldown_ms=float(args.cooldown_ms),
        bootstrap_resamples=int(args.bootstrap_resamples),
        bootstrap_seed=int(args.bootstrap_seed),
        qdrant_snapshot=QdrantConfigSnapshot(collection_name=str(args.collection)),
    )
    output_dir = Path(args.output_dir)
    write_all_outputs(rows=rows, summary=summary, output_dir=output_dir)
    sys.stdout.write(format_terminal_summary(summary))
    return 0


def _metrics_from_retrieval(
    *,
    query: EvalQuery,
    mode: RetrievalMode,
    result: RetrievalLikeResult,
) -> QueryMetrics:
    relevant_doc_ids = tuple(
        doc_id for doc_id, grade in sorted(query.qrels.items()) if grade > 0
    )
    return QueryMetrics(
        query_id=query.query_id,
        category=query.category,
        mode=mode,
        rank_1_doc_id=result.rank_1_doc_id,
        hit_doc_ids=result.hit_doc_ids,
        hit_result_ids=result.hit_result_ids,
        relevant_doc_ids=relevant_doc_ids,
        precision_at_5=precision_at_k(result.hit_doc_ids, query.qrels, 5),
        recall_at_10=recall_at_k(result.hit_doc_ids, query.qrels, 10),
        mrr=reciprocal_rank(result.hit_doc_ids, query.qrels),
        ndcg_at_5=ndcg_at_k(result.hit_doc_ids, query.qrels, 5),
        latency_ms=result.latency_ms,
        retrieval_personality=result.retrieval_personality,
        phase_latencies=result.phase_latencies,
    )


def _build_deltas(
    *,
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> tuple[DeltaResult, ...]:
    metrics = {
        "precision_at_5": (
            [metric.precision_at_5 for metric in dense_metrics],
            [metric.precision_at_5 for metric in hybrid_metrics],
        ),
        "recall_at_10": (
            [metric.recall_at_10 for metric in dense_metrics],
            [metric.recall_at_10 for metric in hybrid_metrics],
        ),
        "mrr": (
            [metric.mrr for metric in dense_metrics],
            [metric.mrr for metric in hybrid_metrics],
        ),
        "ndcg_at_5": (
            [metric.ndcg_at_5 for metric in dense_metrics],
            [metric.ndcg_at_5 for metric in hybrid_metrics],
        ),
        "latency_ms": (
            [metric.latency_ms for metric in dense_metrics],
            [metric.latency_ms for metric in hybrid_metrics],
        ),
    }
    deltas: list[DeltaResult] = []
    for index, (metric, (dense_values, hybrid_values)) in enumerate(metrics.items()):
        dense_ci = bootstrap_ci(
            dense_values,
            n_resamples=bootstrap_resamples,
            rng_seed=bootstrap_seed + index,
        )
        # Use a deterministic offset so dense and hybrid bootstrap streams are
        # independent while remaining reproducible for the same seed.
        hybrid_ci = bootstrap_ci(
            hybrid_values,
            n_resamples=bootstrap_resamples,
            rng_seed=bootstrap_seed + index + 100,
        )
        deltas.append(
            delta_pair(
                _mean(dense_values),
                _mean(hybrid_values),
                metric=metric,
                dense_ci=dense_ci,
                hybrid_ci=hybrid_ci,
            )
        )
    return tuple(deltas)


def _win_loss_tie(
    dense_metrics: Sequence[QueryMetrics],
    hybrid_metrics: Sequence[QueryMetrics],
) -> dict[str, int]:
    assert_paired_query_metrics(dense_metrics, hybrid_metrics)
    hybrid_by_query_id = _metrics_by_query_id(hybrid_metrics)
    wins = losses = ties = 0
    for dense in dense_metrics:
        hybrid = hybrid_by_query_id[dense.query_id]
        dense_score = dense.ndcg_at_5
        hybrid_score = hybrid.ndcg_at_5
        if hybrid_score > dense_score:
            wins += 1
        elif hybrid_score < dense_score:
            losses += 1
        else:
            ties += 1
    return {"hybrid_wins": wins, "dense_wins": losses, "ties": ties}


def _row_to_csv_dict(row: QueryComparisonRow) -> dict[str, str]:
    return {
        "schema_version": row.schema_version,
        "run_id": row.run_id,
        "mode": row.mode,
        "query_id": row.query_id,
        "query_category": row.query_category,
        "rank_1_doc_id": row.rank_1_doc_id,
        "precision_at_5": _fmt_float(row.precision_at_5),
        "recall_at_10": _fmt_float(row.recall_at_10),
        "mrr": _fmt_float(row.mrr),
        "ndcg_at_5": _fmt_float(row.ndcg_at_5),
        "latency_ms": _fmt_float(row.latency_ms),
        "embed_dense_ms": _fmt_float(row.embed_dense_ms),
        "embed_sparse_ms": _fmt_float(row.embed_sparse_ms),
        "search_dense_ms": _fmt_float(row.search_dense_ms),
        "search_sparse_ms": _fmt_float(row.search_sparse_ms),
        "fusion_ms": _fmt_float(row.fusion_ms),
        "total_ms": _fmt_float(row.total_ms),
        "retrieval_personality": row.retrieval_personality,
        "hit_doc_ids": "|".join(row.hit_doc_ids),
        "relevant_doc_ids": "|".join(row.relevant_doc_ids),
        "search_top_k": str(row.search_top_k),
        "return_top_k": str(row.return_top_k),
        "rrf_profile": row.rrf_profile,
        "qdrant_server_version": row.qdrant_server_version,
        "qdrant_client_version": row.qdrant_client_version,
        "ef_search": row.ef_search,
        "strict_mode": row.strict_mode,
    }


def _svg_quality_chart(
    dense: Mapping[str, float],
    hybrid: Mapping[str, float],
    metrics: Sequence[str],
    *,
    x: int,
    y: int,
) -> str:
    bars: list[str] = [
        f'<text x="{x}" y="{y}" class="title">Quality Metrics</text>',
        f'<line x1="{x}" y1="{y + 230}" x2="{x + 480}" y2="{y + 230}" class="axis"/>',
    ]
    for index, metric in enumerate(metrics):
        group_x = x + 20 + index * 110
        dense_h = int(180.0 * dense[metric])
        hybrid_h = int(180.0 * hybrid[metric])
        bars.append(
            f'<rect class="dense" x="{group_x}" y="{y + 230 - dense_h}" width="28" height="{dense_h}"/>'
        )
        bars.append(
            f'<rect class="hybrid" x="{group_x + 34}" y="{y + 230 - hybrid_h}" width="28" height="{hybrid_h}"/>'
        )
        bars.append(
            f'<text x="{group_x}" y="{y + 250}" class="small">{html.escape(metric)}</text>'
        )
    bars.append(f'<text x="{x + 20}" y="{y + 285}" class="small">blue=dense green=hybrid</text>')
    return "\n".join(bars)


def _svg_latency_chart(
    dense: Mapping[str, float],
    hybrid: Mapping[str, float],
    *,
    x: int,
    y: int,
) -> str:
    max_value = max(dense["p50_ms"], dense["p95_ms"], hybrid["p50_ms"], hybrid["p95_ms"], 1.0)
    rows = [f'<text x="{x}" y="{y}" class="title">Latency p50/p95</text>']
    labels = (("p50", dense["p50_ms"], hybrid["p50_ms"]), ("p95", dense["p95_ms"], hybrid["p95_ms"]))
    for index, (label, dense_value, hybrid_value) in enumerate(labels):
        row_y = y + 50 + index * 90
        dense_w = int((dense_value / max_value) * 300.0)
        hybrid_w = int((hybrid_value / max_value) * 300.0)
        rows.append(f'<text x="{x}" y="{row_y}" class="small">{label}</text>')
        rows.append(f'<rect class="dense" x="{x + 60}" y="{row_y - 18}" width="{dense_w}" height="18"/>')
        rows.append(f'<rect class="hybrid" x="{x + 60}" y="{row_y + 8}" width="{hybrid_w}" height="18"/>')
    multiplier = _safe_ratio(hybrid["p95_ms"], dense["p95_ms"])
    rows.append(f'<text x="{x}" y="{y + 235}" class="small">p95 multiplier: {_fmt_float(multiplier)}</text>')
    return "\n".join(rows)


def _svg_delta_waterfall(
    gains: Sequence[Mapping[str, object]],
    regressions: Sequence[Mapping[str, object]],
    *,
    x: int,
    y: int,
) -> str:
    rows = [f'<text x="{x}" y="{y}" class="title">Per-query NDCG@5 Delta</text>']
    merged = list(gains[:3]) + list(regressions[:3])
    zero_x = x + 240
    rows.append(f'<line x1="{zero_x}" y1="{y + 25}" x2="{zero_x}" y2="{y + 225}" class="axis"/>')
    for index, row in enumerate(merged):
        delta = _row_float(row, "delta_ndcg_at_5")
        bar_w = int(abs(delta) * 160.0)
        row_y = y + 50 + index * 28
        color = "pos" if delta >= 0.0 else "neg"
        bar_x = zero_x if delta >= 0.0 else zero_x - bar_w
        rows.append(f'<text x="{x}" y="{row_y + 13}" class="small">{html.escape(str(row["query_id"]))}</text>')
        rows.append(f'<rect class="{color}" x="{bar_x}" y="{row_y}" width="{bar_w}" height="16"/>')
    return "\n".join(rows)


def _svg_category_table(
    breakdown: Mapping[str, Mapping[str, float]],
    *,
    x: int,
    y: int,
) -> str:
    rows = [f'<text x="{x}" y="{y}" class="title">Category Breakdown</text>']
    rows.append(f'<text x="{x}" y="{y + 30}" class="small">category | delta recall@10 | delta ndcg@5 | W/L/T</text>')
    for index, (category, values) in enumerate(sorted(breakdown.items())):
        row_y = y + 58 + index * 24
        label = (
            f"{category} | {_fmt_signed(values['delta_recall_at_10'])} | "
            f"{_fmt_signed(values['delta_ndcg_at_5'])} | "
            f"{int(values['wins'])}/{int(values['losses'])}/{int(values['ties'])}"
        )
        rows.append(f'<text x="{x}" y="{row_y}" class="small">{html.escape(label)}</text>')
    return "\n".join(rows)


def _svg_personality_bar(
    counts: Mapping[str, int],
    *,
    x: int,
    y: int,
) -> str:
    rows = [f'<text x="{x}" y="{y}" class="title">Retrieval Personality</text>']
    total = max(sum(counts.values()), 1)
    current_x = x
    colors = ("#27AE60", "#2F80ED", "#F2C94C", "#9B51E0", "#EB5757", "#828282")
    for index, (label, count) in enumerate(sorted(counts.items())):
        width = int((count / total) * 430.0)
        rows.append(
            f'<rect x="{current_x}" y="{y + 35}" width="{width}" height="30" fill="{colors[index % len(colors)]}"/>'
        )
        rows.append(
            f'<text x="{x}" y="{y + 95 + index * 18}" class="small">{html.escape(label)}: {count}</text>'
        )
        current_x += width
    return "\n".join(rows)


def _svg_quality_vs_delta_scatter(
    gains: Sequence[Mapping[str, object]],
    regressions: Sequence[Mapping[str, object]],
    *,
    x: int,
    y: int,
) -> str:
    rows = [f'<text x="{x}" y="{y}" class="title">Quality Gain vs Latency Overhead</text>']
    rows.append(f'<rect x="{x}" y="{y + 25}" width="420" height="180" fill="none" stroke="#333"/>')
    rows.append(f'<text x="{x + 10}" y="{y + 55}" class="small">points are query ids, ordered by NDCG delta</text>')
    merged = list(gains[:3]) + list(regressions[:3])
    for index, row in enumerate(merged):
        px = x + 40 + index * 55
        py = y + 125 - int(_row_float(row, "delta_ndcg_at_5") * 55.0)
        rows.append(f'<circle cx="{px}" cy="{py}" r="5" fill="#27AE60"/>')
        rows.append(f'<text x="{px + 8}" y="{py + 4}" class="small">{html.escape(str(row["query_id"]))}</text>')
    return "\n".join(rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare dense-only and hybrid retrieval.")
    parser.add_argument("--collection", default="quimera_knowledge_v2")
    parser.add_argument("--queries", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--search-top-k", type=int, default=DEFAULT_SEARCH_TOP_K)
    parser.add_argument("--return-top-k", type=int, default=DEFAULT_RETURN_TOP_K)
    parser.add_argument("--cooldown-ms", type=float, default=0.0)
    parser.add_argument("--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    parser.add_argument("--include-debug-text", action="store_true")
    parser.add_argument("--run-live", "--execute", action="store_true", dest="run_live")
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--rrf-k", type=float, default=DEFAULT_RRF_K)
    parser.add_argument("--dense-weight", type=float, default=DEFAULT_DENSE_WEIGHT)
    parser.add_argument("--sparse-weight", type=float, default=DEFAULT_SPARSE_WEIGHT)
    return parser


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return value


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _validate_finite_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean):
        raise ValueError(f"{field_name} must be finite")
    return clean


def _validate_non_negative_float(value: float, field_name: str) -> float:
    clean = _validate_finite_float(value, field_name)
    if clean < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return clean


def _validate_percentile(value: float) -> float:
    clean = _validate_finite_float(value, "percentile")
    if clean < 0.0 or clean > 100.0:
        raise ValueError("percentile must be between 0 and 100")
    return clean


def _validate_confidence(value: float) -> float:
    clean = _validate_finite_float(value, "confidence")
    if clean <= 0.0 or clean >= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return clean


def _coerce_query_category(value: QueryCategory) -> QueryCategory:
    if isinstance(value, QueryCategory):
        return value
    raise TypeError("category must be QueryCategory")


def _coerce_retrieval_mode(value: RetrievalMode) -> RetrievalMode:
    if isinstance(value, RetrievalMode):
        return value
    raise TypeError("mode must be RetrievalMode")


def _freeze_qrels(qrels: Mapping[str, int]) -> Mapping[str, int]:
    clean: dict[str, int] = {}
    for doc_id, grade in qrels.items():
        clean_doc_id = _validate_text(doc_id, "qrel doc_id")
        if isinstance(grade, bool) or not isinstance(grade, int):
            raise TypeError("qrel grade must be an integer")
        if grade not in {0, 1, 2}:
            raise ValueError("qrel grade must be one of 0, 1 or 2")
        clean[clean_doc_id] = grade
    return MappingProxyType(clean)


def _sorted_numeric_values(values: Sequence[float]) -> list[float]:
    return sorted(_validate_finite_float(value, "value") for value in values)


def _mean(values: Sequence[float]) -> float:
    clean_values = [_validate_finite_float(value, "value") for value in values]
    if not clean_values:
        return 0.0
    return sum(clean_values) / float(len(clean_values))


def _ci_overlap(
    dense_ci: tuple[float, float] | None,
    hybrid_ci: tuple[float, float] | None,
) -> bool:
    if dense_ci is None or hybrid_ci is None:
        return False
    return not (dense_ci[1] < hybrid_ci[0] or hybrid_ci[1] < dense_ci[0])


def _safe_ratio(numerator: float, denominator: float) -> float:
    clean_numerator = _validate_non_negative_float(numerator, "numerator")
    clean_denominator = _validate_non_negative_float(denominator, "denominator")
    if clean_denominator <= EPSILON:
        return math.inf if clean_numerator > EPSILON else 1.0
    return clean_numerator / clean_denominator


def _nested_mapping_to_dict(values: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    return {key: dict(value) for key, value in values.items()}


def _fmt_float(value: float) -> str:
    rendered = f"{_validate_finite_float(value, 'value'):.6f}".rstrip("0").rstrip(".")
    if "." not in rendered:
        return f"{rendered}.0"
    return rendered


def _fmt_signed(value: float) -> str:
    clean = _validate_finite_float(value, "value")
    return f"{clean:+.6f}".rstrip("0").rstrip(".")


def _ascii_bar(value: float) -> str:
    clean = _validate_finite_float(value, "value")
    width = min(20, int(abs(clean) * 20.0))
    return ("+" if clean >= 0.0 else "-") + ("#" * width)


def _assert_safe_serialized_payload(payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _assert_safe_text(text)


def _assert_safe_text(text: str) -> None:
    lowered = text.casefold()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        if _contains_token(lowered, token):
            raise ValueError(f"unsafe output token detected: {token}")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _row_float(row: Mapping[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _metrics_by_query_id(metrics: Sequence[QueryMetrics]) -> dict[str, QueryMetrics]:
    by_query_id: dict[str, QueryMetrics] = {}
    for metric in metrics:
        if metric.query_id in by_query_id:
            raise ValueError(f"duplicate query_id in metrics: {metric.query_id}")
        by_query_id[metric.query_id] = metric
    return by_query_id


def _contains_token(text: str, token: str) -> bool:
    start = 0
    while True:
        index = text.find(token, start)
        if index < 0:
            return False
        before = text[index - 1] if index > 0 else ""
        after_index = index + len(token)
        after = text[after_index] if after_index < len(text) else ""
        if not _is_identifier_char(before) and not _is_identifier_char(after):
            return True
        start = index + len(token)


def _is_identifier_char(value: str) -> bool:
    return bool(value) and (value.isalnum() or value == "_")


__all__ = [
    "SCHEMA_VERSION",
    "CSV_SCHEMA_VERSION",
    "CSV_COLUMNS",
    "RetrievalMode",
    "QueryCategory",
    "Verdict",
    "EvalQuery",
    "EvaluationRun",
    "PhaseLatencies",
    "RetrievalLikeResult",
    "RetrieverRunnerProtocol",
    "QueryMetrics",
    "QueryComparisonRow",
    "HybridDecisionThresholds",
    "DeltaResult",
    "ComparisonVerdict",
    "QdrantConfigSnapshot",
    "ComparisonSummary",
    "StaticRetrieverRunner",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "dcg_at_k",
    "ndcg_at_k",
    "percentile_nearest_rank",
    "percentile_interpolated",
    "bootstrap_ci",
    "delta_pair",
    "classify_retrieval_effect",
    "run_mode",
    "assert_paired_query_metrics",
    "assert_runs_comparable",
    "compute_corpus_hash",
    "make_run_id",
    "build_evaluation_run",
    "build_query_rows",
    "build_summary",
    "aggregate_metrics",
    "latency_summary",
    "category_breakdown",
    "retrieval_personality_counts",
    "top_query_deltas",
    "decide_hybrid_promotion",
    "decide_hybrid_promotion_from_parts",
    "write_csv",
    "write_json",
    "write_markdown",
    "write_svg",
    "render_markdown_report",
    "render_svg_dashboard",
    "format_terminal_summary",
    "write_all_outputs",
    "load_eval_queries",
    "default_eval_queries",
    "default_static_runners",
    "compare_dense_vs_hybrid",
    "main",
]
