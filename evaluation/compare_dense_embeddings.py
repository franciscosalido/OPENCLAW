"""A/B benchmark contract for dense embedding profiles.

PR-04C compares the current dense baseline against the Qwen3 dense candidate
using identical benchmark inputs. This module is intentionally orchestration
only: profile execution is injected through ``DenseProfileRunner`` so unit
tests never download models and the benchmark cannot silently mutate runtime
retrieval code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

from loguru import logger

from evaluation import (
    latency_percentiles,
    mean_ndcg_at_k,
    mean_precision_at_k,
    mean_recall_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.run_dense_baseline import (
    BenchmarkQuery,
    load_benchmark_queries,
    load_expected_results,
)


RUNNER_VERSION = "rag-1a-pr04c"
DEFAULT_BASELINE_PROFILE = "nomic_dense_v1"
DEFAULT_CANDIDATE_PROFILE = "qwen3_dense_8b_v1"
DEFAULT_TOP_K = 20
DEFAULT_CUTOFF_PRECISION = 5
DEFAULT_CUTOFF_RECALL = 10
DEFAULT_CUTOFF_NDCG = 5
DEFAULT_BENCHMARK_FILE = Path("evaluation") / "benchmark_queries.yaml"
DEFAULT_EXPECTED_RESULTS_FILE = Path("evaluation") / "expected_results.yaml"
DEFAULT_RESULTS_DIR = Path("evaluation") / "results"
DEFAULT_CSV_FILENAME = "dense_embedding_ab.csv"
DEFAULT_JSON_FILENAME = "dense_embedding_ab.json"
DEFAULT_MARKDOWN_FILENAME = "dense_embedding_ab.md"
DEFAULT_ADR_PATH = Path("docs") / "ADR" / "0003-qwen3-embedding-baseline.md"
EPSILON = 1e-8


@dataclass(frozen=True)
class DenseEmbeddingBenchmark:
    """Benchmark inputs shared by all dense profile runs."""

    queries: tuple[BenchmarkQuery, ...]
    expected_results: Mapping[str, Mapping[str, float]]
    benchmark_hash: str
    expected_results_hash: str


@dataclass(frozen=True)
class DenseProfileQueryResult:
    """Metadata-only per-query output from one dense profile runner."""

    query_id: str
    retrieved_ids: tuple[str, ...]
    scores: tuple[float, ...]
    embedding_latency_ms: float
    query_latency_ms: float
    ingest_latency_ms: float
    status: Literal["ok", "error"] = "ok"
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DenseProfileRun:
    """Raw profile run output before aggregate metrics are computed."""

    profile_id: str
    dimensions: int
    collection_size: int
    benchmark_hash: str
    corpus_hash: str
    query_results: tuple[DenseProfileQueryResult, ...]


@dataclass(frozen=True)
class DenseProfileResult:
    """Aggregate benchmark result for one dense profile."""

    profile_id: str
    precision_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_5: float
    query_latency_p50_ms: float
    query_latency_p95_ms: float
    embedding_latency_p50_ms: float
    embedding_latency_p95_ms: float
    ingest_latency_p50_ms: float
    ingest_latency_p95_ms: float
    dimensions: int
    collection_size: int
    benchmark_hash: str
    corpus_hash: str


@dataclass(frozen=True)
class PromotionThresholds:
    """Decision thresholds for promoting Qwen3 as dense baseline."""

    min_recall10_relative_gain: float = 0.10
    min_ndcg5_relative_gain: float = 0.05
    max_query_p95_latency_multiplier: float = 3.0
    max_embedding_p95_latency_multiplier: float = 10.0


@dataclass(frozen=True)
class PromotionDecision:
    """Decision gate result for the dense profile A/B benchmark."""

    promote_qwen3_dense: bool
    accepted_profile: str
    candidate_profile: str
    reason: str
    thresholds: PromotionThresholds


@dataclass(frozen=True)
class ProfileEvaluationRow:
    """Computed per-query metrics for CSV/JSON output."""

    profile_id: str
    query_id: str
    category: str
    status: Literal["ok", "error"]
    precision_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_5: float
    embedding_latency_ms: float
    query_latency_ms: float
    ingest_latency_ms: float
    total_latency_ms: float
    top_k: int
    retrieved_ids: tuple[str, ...]
    scores: tuple[float, ...]
    hit_ids: tuple[str, ...]
    hit_scores: tuple[float, ...]
    relevance_scores: tuple[float, ...]
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DenseEmbeddingABConfig:
    """Configuration for one dense embedding A/B benchmark run."""

    benchmark_file: Path = DEFAULT_BENCHMARK_FILE
    expected_results_file: Path = DEFAULT_EXPECTED_RESULTS_FILE
    output_dir: Path = DEFAULT_RESULTS_DIR
    adr_path: Path = DEFAULT_ADR_PATH
    baseline_profile: str = DEFAULT_BASELINE_PROFILE
    candidate_profile: str = DEFAULT_CANDIDATE_PROFILE
    top_k: int = DEFAULT_TOP_K
    cutoff_precision: int = DEFAULT_CUTOFF_PRECISION
    cutoff_recall: int = DEFAULT_CUTOFF_RECALL
    cutoff_ndcg: int = DEFAULT_CUTOFF_NDCG

    def normalized(self) -> DenseEmbeddingABConfig:
        """Return a validated config copy."""
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if self.cutoff_precision <= 0:
            raise ValueError("cutoff_precision must be greater than zero")
        if self.cutoff_recall <= 0:
            raise ValueError("cutoff_recall must be greater than zero")
        if self.cutoff_ndcg <= 0:
            raise ValueError("cutoff_ndcg must be greater than zero")
        max_cutoff = max(self.cutoff_precision, self.cutoff_recall, self.cutoff_ndcg)
        if self.top_k <= max_cutoff:
            raise ValueError(
                "top_k must be greater than all metric cutoffs "
                f"(max cutoff is {max_cutoff})"
            )
        if not self.baseline_profile.strip():
            raise ValueError("baseline_profile must not be empty")
        if not self.candidate_profile.strip():
            raise ValueError("candidate_profile must not be empty")
        if self.baseline_profile == self.candidate_profile:
            raise ValueError("baseline_profile and candidate_profile must differ")
        return self


@dataclass(frozen=True)
class DenseEmbeddingABPaths:
    """Artifacts written by the A/B benchmark."""

    csv_path: Path
    json_path: Path
    markdown_path: Path
    adr_path: Path


@dataclass(frozen=True)
class DenseEmbeddingABResult:
    """Final A/B benchmark result."""

    baseline: DenseProfileResult
    candidate: DenseProfileResult
    decision: PromotionDecision
    rows: tuple[ProfileEvaluationRow, ...]
    paths: DenseEmbeddingABPaths


class DenseProfileRunner(Protocol):
    """Profile runner injected by tests or future runtime wiring."""

    def run(
        self,
        benchmark: DenseEmbeddingBenchmark,
        *,
        profile_id: str,
        top_k: int,
    ) -> DenseProfileRun:
        """Run one dense profile against ``benchmark``."""
        ...


def load_benchmark(
    benchmark_file: Path = DEFAULT_BENCHMARK_FILE,
    expected_results_file: Path = DEFAULT_EXPECTED_RESULTS_FILE,
) -> DenseEmbeddingBenchmark:
    """Load PR-01 benchmark inputs and compute file hashes."""
    queries = tuple(load_benchmark_queries(benchmark_file))
    expected_results = load_expected_results(expected_results_file)
    _validate_expected_compatibility(queries, expected_results)
    return DenseEmbeddingBenchmark(
        queries=queries,
        expected_results=expected_results,
        benchmark_hash=_sha256_file(benchmark_file),
        expected_results_hash=_sha256_file(expected_results_file),
    )


def compare_dense_embeddings(
    *,
    baseline_runner: DenseProfileRunner,
    candidate_runner: DenseProfileRunner,
    config: DenseEmbeddingABConfig,
    thresholds: PromotionThresholds = PromotionThresholds(),
) -> DenseEmbeddingABResult:
    """Run the dense embedding A/B benchmark and write artifacts."""
    active_config = config.normalized()
    benchmark = load_benchmark(
        active_config.benchmark_file,
        active_config.expected_results_file,
    )

    baseline_run = baseline_runner.run(
        benchmark,
        profile_id=active_config.baseline_profile,
        top_k=active_config.top_k,
    )
    candidate_run = candidate_runner.run(
        benchmark,
        profile_id=active_config.candidate_profile,
        top_k=active_config.top_k,
    )
    _validate_profile_run(
        run=baseline_run,
        expected_profile=active_config.baseline_profile,
        benchmark=benchmark,
    )
    _validate_profile_run(
        run=candidate_run,
        expected_profile=active_config.candidate_profile,
        benchmark=benchmark,
    )

    baseline_rows = evaluate_profile_run(baseline_run, benchmark, active_config)
    candidate_rows = evaluate_profile_run(candidate_run, benchmark, active_config)
    baseline = summarize_profile_run(
        baseline_run,
        baseline_rows,
        benchmark,
        active_config,
    )
    candidate = summarize_profile_run(
        candidate_run,
        candidate_rows,
        benchmark,
        active_config,
    )
    ensure_fair_comparison(baseline, candidate)
    decision = decide_promotion(baseline, candidate, thresholds)

    paths = _output_paths(active_config)
    active_config.output_dir.mkdir(parents=True, exist_ok=True)
    paths.adr_path.parent.mkdir(parents=True, exist_ok=True)
    rows = baseline_rows + candidate_rows
    write_csv(rows, paths.csv_path)
    write_json(
        baseline=baseline,
        candidate=candidate,
        decision=decision,
        rows=rows,
        benchmark=benchmark,
        path=paths.json_path,
    )
    write_markdown(
        baseline=baseline,
        candidate=candidate,
        decision=decision,
        path=paths.markdown_path,
    )
    write_adr(
        baseline=baseline,
        candidate=candidate,
        decision=decision,
        path=paths.adr_path,
    )
    return DenseEmbeddingABResult(
        baseline=baseline,
        candidate=candidate,
        decision=decision,
        rows=rows,
        paths=paths,
    )


def evaluate_profile_run(
    run: DenseProfileRun,
    benchmark: DenseEmbeddingBenchmark,
    config: DenseEmbeddingABConfig,
) -> tuple[ProfileEvaluationRow, ...]:
    """Compute per-query metrics for a raw dense profile run."""
    query_by_id = {query.query_id: query for query in benchmark.queries}
    rows: list[ProfileEvaluationRow] = []
    for result in run.query_results:
        query = query_by_id[result.query_id]
        expected_ids = frozenset(query.expected_doc_ids)
        relevance_scores = tuple(
            _relevance_scores(
                query_id=query.query_id,
                retrieved_ids=result.retrieved_ids,
                expected_results=benchmark.expected_results,
                cutoff=config.cutoff_ndcg,
            )
        )
        if result.status == "ok":
            precision = precision_at_k(
                result.retrieved_ids,
                expected_ids,
                config.cutoff_precision,
            )
            recall = recall_at_k(
                result.retrieved_ids,
                expected_ids,
                config.cutoff_recall,
            )
            rr = reciprocal_rank(result.retrieved_ids, expected_ids)
            ndcg = ndcg_at_k(relevance_scores, config.cutoff_ndcg)
        else:
            precision = 0.0
            recall = 0.0
            rr = 0.0
            ndcg = 0.0

        hit_pairs = [
            (doc_id, result.scores[index])
            for index, doc_id in enumerate(result.retrieved_ids)
            if doc_id in expected_ids and index < len(result.scores)
        ]
        total_latency = (
            result.embedding_latency_ms
            + result.query_latency_ms
            + result.ingest_latency_ms
        )
        rows.append(
            ProfileEvaluationRow(
                profile_id=run.profile_id,
                query_id=query.query_id,
                category=query.category,
                status=result.status,
                precision_at_5=precision,
                recall_at_10=recall,
                mrr=rr,
                ndcg_at_5=ndcg,
                embedding_latency_ms=result.embedding_latency_ms,
                query_latency_ms=result.query_latency_ms,
                ingest_latency_ms=result.ingest_latency_ms,
                total_latency_ms=total_latency,
                top_k=config.top_k,
                retrieved_ids=result.retrieved_ids,
                scores=result.scores,
                hit_ids=tuple(doc_id for doc_id, _ in hit_pairs),
                hit_scores=tuple(score for _, score in hit_pairs),
                relevance_scores=relevance_scores,
                error_type=result.error_type,
                error_message=result.error_message,
            )
        )
    return tuple(rows)


def summarize_profile_run(
    run: DenseProfileRun,
    rows: Sequence[ProfileEvaluationRow],
    benchmark: DenseEmbeddingBenchmark,
    config: DenseEmbeddingABConfig,
) -> DenseProfileResult:
    """Aggregate per-query rows into one profile result."""
    ok_rows = [row for row in rows if row.status == "ok"]
    if not ok_rows:
        latency = {50: 0.0, 95: 0.0}
        return DenseProfileResult(
            profile_id=run.profile_id,
            precision_at_5=0.0,
            recall_at_10=0.0,
            mrr=0.0,
            ndcg_at_5=0.0,
            query_latency_p50_ms=0.0,
            query_latency_p95_ms=0.0,
            embedding_latency_p50_ms=0.0,
            embedding_latency_p95_ms=0.0,
            ingest_latency_p50_ms=latency[50],
            ingest_latency_p95_ms=latency[95],
            dimensions=run.dimensions,
            collection_size=run.collection_size,
            benchmark_hash=run.benchmark_hash,
            corpus_hash=run.corpus_hash,
        )

    expected_ids_by_query = {
        query.query_id: frozenset(query.expected_doc_ids)
        for query in benchmark.queries
    }
    precision_recall_inputs = [
        (row.retrieved_ids, expected_ids_by_query[row.query_id])
        for row in ok_rows
    ]
    rr_scores = [row.mrr for row in ok_rows]
    ndcg_inputs = [row.relevance_scores for row in ok_rows]
    query_latency = latency_percentiles(
        [row.query_latency_ms for row in ok_rows],
        (50, 95),
    )
    embedding_latency = latency_percentiles(
        [row.embedding_latency_ms for row in ok_rows],
        (50, 95),
    )
    ingest_latency = latency_percentiles(
        [row.ingest_latency_ms for row in ok_rows],
        (50, 95),
    )
    return DenseProfileResult(
        profile_id=run.profile_id,
        precision_at_5=mean_precision_at_k(
            precision_recall_inputs,
            config.cutoff_precision,
        ),
        recall_at_10=mean_recall_at_k(
            precision_recall_inputs,
            config.cutoff_recall,
        ),
        mrr=mean_reciprocal_rank(rr_scores),
        ndcg_at_5=mean_ndcg_at_k(ndcg_inputs, config.cutoff_ndcg),
        query_latency_p50_ms=query_latency[50],
        query_latency_p95_ms=query_latency[95],
        embedding_latency_p50_ms=embedding_latency[50],
        embedding_latency_p95_ms=embedding_latency[95],
        ingest_latency_p50_ms=ingest_latency[50],
        ingest_latency_p95_ms=ingest_latency[95],
        dimensions=run.dimensions,
        collection_size=run.collection_size,
        benchmark_hash=run.benchmark_hash,
        corpus_hash=run.corpus_hash,
    )


def ensure_fair_comparison(
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
) -> None:
    """Raise if profile results were not produced from identical inputs."""
    if baseline.benchmark_hash != candidate.benchmark_hash:
        raise ValueError("A/B benchmark must use identical benchmark queries")
    if baseline.corpus_hash != candidate.corpus_hash:
        raise ValueError("A/B benchmark must use identical corpus snapshot")


def decide_promotion(
    nomic: DenseProfileResult,
    qwen3: DenseProfileResult,
    thresholds: PromotionThresholds = PromotionThresholds(),
) -> PromotionDecision:
    """Apply the PR-04C quality/latency gate."""
    recall_gain = _relative_gain(qwen3.recall_at_10, nomic.recall_at_10)
    ndcg_gain = _relative_gain(qwen3.ndcg_at_5, nomic.ndcg_at_5)
    query_p95_multiplier = _latency_multiplier(
        qwen3.query_latency_p95_ms,
        nomic.query_latency_p95_ms,
    )
    embedding_p95_multiplier = _latency_multiplier(
        qwen3.embedding_latency_p95_ms,
        nomic.embedding_latency_p95_ms,
    )
    promote = (
        recall_gain >= thresholds.min_recall10_relative_gain
        and ndcg_gain >= thresholds.min_ndcg5_relative_gain
        and query_p95_multiplier <= thresholds.max_query_p95_latency_multiplier
        and embedding_p95_multiplier
        <= thresholds.max_embedding_p95_latency_multiplier
    )
    if promote:
        accepted = qwen3.profile_id
        reason = (
            "Qwen3 met quality thresholds within latency limits: "
            f"recall_gain={_format_ratio(recall_gain)}, "
            f"ndcg_gain={_format_ratio(ndcg_gain)}, "
            f"query_p95_multiplier={_format_multiplier(query_p95_multiplier)}, "
            "embedding_p95_multiplier="
            f"{_format_multiplier(embedding_p95_multiplier)}."
        )
    else:
        accepted = nomic.profile_id
        reason = (
            "Qwen3 did not meet all promotion thresholds: "
            f"recall_gain={_format_ratio(recall_gain)}, "
            f"ndcg_gain={_format_ratio(ndcg_gain)}, "
            f"query_p95_multiplier={_format_multiplier(query_p95_multiplier)}, "
            "embedding_p95_multiplier="
            f"{_format_multiplier(embedding_p95_multiplier)}."
        )
    return PromotionDecision(
        promote_qwen3_dense=promote,
        accepted_profile=accepted,
        candidate_profile=qwen3.profile_id,
        reason=reason,
        thresholds=thresholds,
    )


def write_csv(rows: Sequence[ProfileEvaluationRow], path: Path) -> None:
    """Write per-query A/B rows without query text or document content."""
    fieldnames = [
        "profile_id",
        "query_id",
        "category",
        "status",
        "precision_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_5",
        "embedding_latency_ms",
        "query_latency_ms",
        "ingest_latency_ms",
        "total_latency_ms",
        "top_k",
        "hit_ids",
        "hit_scores",
        "retrieved_ids",
        "scores",
        "error_type",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "profile_id": row.profile_id,
                    "query_id": row.query_id,
                    "category": row.category,
                    "status": row.status,
                    "precision_at_5": row.precision_at_5,
                    "recall_at_10": row.recall_at_10,
                    "mrr": row.mrr,
                    "ndcg_at_5": row.ndcg_at_5,
                    "embedding_latency_ms": row.embedding_latency_ms,
                    "query_latency_ms": row.query_latency_ms,
                    "ingest_latency_ms": row.ingest_latency_ms,
                    "total_latency_ms": row.total_latency_ms,
                    "top_k": row.top_k,
                    "hit_ids": "|".join(row.hit_ids),
                    "hit_scores": "|".join(str(score) for score in row.hit_scores),
                    "retrieved_ids": "|".join(row.retrieved_ids),
                    "scores": "|".join(str(score) for score in row.scores),
                    "error_type": row.error_type or "",
                    "error_message": row.error_message or "",
                }
            )


def write_json(
    *,
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
    decision: PromotionDecision,
    rows: Sequence[ProfileEvaluationRow],
    benchmark: DenseEmbeddingBenchmark,
    path: Path,
) -> None:
    """Write JSON summary with decision gate and compact rows."""
    payload = {
        "runner_version": RUNNER_VERSION,
        "benchmark_hash": benchmark.benchmark_hash,
        "expected_results_hash": benchmark.expected_results_hash,
        "profiles": [
            _profile_result_to_dict(baseline),
            _profile_result_to_dict(candidate),
        ],
        "decision_gate": _decision_to_dict(decision),
        "results": [_row_to_dict(row) for row in rows],
    }
    _assert_safe_output(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown(
    *,
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
    decision: PromotionDecision,
    path: Path,
) -> None:
    """Write a human-readable A/B report with tables and Mermaid charts."""
    path.write_text(
        render_markdown_report(
            baseline=baseline,
            candidate=candidate,
            decision=decision,
        ),
        encoding="utf-8",
    )


def render_markdown_report(
    *,
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
    decision: PromotionDecision,
) -> str:
    """Return the Markdown report body."""
    faster_query = _winner_lower(
        baseline.profile_id,
        candidate.profile_id,
        baseline.query_latency_p95_ms,
        candidate.query_latency_p95_ms,
    )
    faster_embedding = _winner_lower(
        baseline.profile_id,
        candidate.profile_id,
        baseline.embedding_latency_p95_ms,
        candidate.embedding_latency_p95_ms,
    )
    more_precise = _winner_higher(
        baseline.profile_id,
        candidate.profile_id,
        baseline.recall_at_10,
        candidate.recall_at_10,
    )
    quality_rows = [
        _quality_row("Precision@5", baseline.precision_at_5, candidate.precision_at_5),
        _quality_row("Recall@10", baseline.recall_at_10, candidate.recall_at_10),
        _quality_row("MRR", baseline.mrr, candidate.mrr),
        _quality_row("NDCG@5", baseline.ndcg_at_5, candidate.ndcg_at_5),
    ]
    latency_rows = [
        _latency_row(
            "Query p50",
            baseline.query_latency_p50_ms,
            candidate.query_latency_p50_ms,
        ),
        _latency_row(
            "Query p95",
            baseline.query_latency_p95_ms,
            candidate.query_latency_p95_ms,
        ),
        _latency_row(
            "Embedding p50",
            baseline.embedding_latency_p50_ms,
            candidate.embedding_latency_p50_ms,
        ),
        _latency_row(
            "Embedding p95",
            baseline.embedding_latency_p95_ms,
            candidate.embedding_latency_p95_ms,
        ),
    ]
    return f"""# Dense Embedding A/B Benchmark — Nomic vs Qwen3-8B

## Resumo

- Baseline: `{baseline.profile_id}` ({baseline.dimensions} dimensões).
- Candidato: `{candidate.profile_id}` ({candidate.dimensions} dimensões).
- Benchmark hash: `{baseline.benchmark_hash}`.
- Corpus hash: `{baseline.corpus_hash}`.

## Métricas de Qualidade

| Métrica | Nomic | Qwen3-8B | Diferença | Vencedor |
|---|---:|---:|---:|---|
{chr(10).join(quality_rows)}

```mermaid
xychart-beta
  title "Qualidade de Retrieval — maior é melhor"
  x-axis ["Precision@5", "Recall@10", "MRR", "NDCG@5"]
  y-axis "Score" 0 --> 1
  bar "Nomic" [{_score(baseline.precision_at_5)}, {_score(baseline.recall_at_10)}, {_score(baseline.mrr)}, {_score(baseline.ndcg_at_5)}]
  bar "Qwen3-8B" [{_score(candidate.precision_at_5)}, {_score(candidate.recall_at_10)}, {_score(candidate.mrr)}, {_score(candidate.ndcg_at_5)}]
```

## Latência

| Métrica | Nomic (ms) | Qwen3-8B (ms) | Multiplicador | Vencedor |
|---|---:|---:|---:|---|
{chr(10).join(latency_rows)}

```mermaid
xychart-beta
  title "Latência p95 (ms) — menor é melhor"
  x-axis ["Query p95", "Embedding p95"]
  y-axis "ms" 0 --> {_latency_axis_max(baseline, candidate)}
  bar "Nomic" [{_ms(baseline.query_latency_p95_ms)}, {_ms(baseline.embedding_latency_p95_ms)}]
  bar "Qwen3-8B" [{_ms(candidate.query_latency_p95_ms)}, {_ms(candidate.embedding_latency_p95_ms)}]
```

## Veredito Humano

- Mais preciso: **{more_precise}**.
- Mais rápido em query p95: **{faster_query}**.
- Mais rápido em embedding p95: **{faster_embedding}**.
- Decisão: `{decision.accepted_profile}`.
- `promote_qwen3_dense`: `{str(decision.promote_qwen3_dense).lower()}`.
- Motivo: {decision.reason}

## Gate de Decisão

```text
promote_qwen3_dense: {str(decision.promote_qwen3_dense).lower()}
accepted_profile: {decision.accepted_profile}
candidate_profile: {decision.candidate_profile}
reason: {decision.reason}
```
"""


def write_adr(
    *,
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
    decision: PromotionDecision,
    path: Path,
) -> None:
    """Write the short ADR recording the A/B decision."""
    status = "Accepted" if decision.promote_qwen3_dense else "Rejected"
    path.write_text(
        f"""# ADR-0003 — Qwen3 Dense Embedding Baseline

## Status

{status} for Qwen3 dense baseline promotion.

## Contexto

O RAG-1A compara `{baseline.profile_id}` contra `{candidate.profile_id}`
usando o mesmo corpus e as mesmas queries do benchmark financeiro brasileiro.

## Resultado

- Recall@10 baseline: {_score(baseline.recall_at_10)}
- Recall@10 candidato: {_score(candidate.recall_at_10)}
- NDCG@5 baseline: {_score(baseline.ndcg_at_5)}
- NDCG@5 candidato: {_score(candidate.ndcg_at_5)}
- Query p95 baseline: {_ms(baseline.query_latency_p95_ms)} ms
- Query p95 candidato: {_ms(candidate.query_latency_p95_ms)} ms
- Embedding p95 baseline: {_ms(baseline.embedding_latency_p95_ms)} ms
- Embedding p95 candidato: {_ms(candidate.embedding_latency_p95_ms)} ms

## Decisão

- accepted_profile: `{decision.accepted_profile}`
- promote_qwen3_dense: `{str(decision.promote_qwen3_dense).lower()}`

## Motivo

{decision.reason}

## Fora de Escopo

- BM25 e hybrid search.
- Reranker.
- Agentic RAG e multi-tool orchestration.
- Alterar `active_profile` de produção neste PR.
""",
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI args for the A/B benchmark contract."""
    parser = argparse.ArgumentParser(
        description="Compare dense embedding profiles for RAG-1A PR-04C."
    )
    parser.add_argument("--baseline-profile", default=DEFAULT_BASELINE_PROFILE)
    parser.add_argument("--candidate-profile", default=DEFAULT_CANDIDATE_PROFILE)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK_FILE)
    parser.add_argument(
        "--expected-results",
        type=Path,
        default=DEFAULT_EXPECTED_RESULTS_FILE,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--adr-path", type=Path, default=DEFAULT_ADR_PATH)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate CLI args and explain the required runner wiring.

    PR-04C keeps production retrieval untouched. Real profile runners are
    intentionally injected by future wiring or tests, not auto-created here.
    """
    args = parse_args(argv)
    DenseEmbeddingABConfig(
        benchmark_file=args.benchmark,
        expected_results_file=args.expected_results,
        output_dir=args.output_dir,
        adr_path=args.adr_path,
        baseline_profile=str(args.baseline_profile),
        candidate_profile=str(args.candidate_profile),
        top_k=int(args.top_k),
    ).normalized()
    logger.error(
        "dense embedding A/B runner requires injected profile runners; "
        "no production retrieval wiring is changed in PR-04C"
    )
    return 2


def _validate_profile_run(
    *,
    run: DenseProfileRun,
    expected_profile: str,
    benchmark: DenseEmbeddingBenchmark,
) -> None:
    if run.profile_id != expected_profile:
        raise ValueError(
            f"profile runner returned {run.profile_id!r}, expected {expected_profile!r}"
        )
    if run.dimensions <= 0:
        raise ValueError("profile dimensions must be greater than zero")
    if run.collection_size < 0:
        raise ValueError("collection_size cannot be negative")
    if run.benchmark_hash != benchmark.benchmark_hash:
        raise ValueError("profile run benchmark hash does not match loaded benchmark")
    query_ids = {query.query_id for query in benchmark.queries}
    result_ids = {row.query_id for row in run.query_results}
    missing = query_ids - result_ids
    extra = result_ids - query_ids
    if missing:
        raise ValueError(f"profile run missing query ids: {sorted(missing)}")
    if extra:
        raise ValueError(f"profile run returned unknown query ids: {sorted(extra)}")


def _validate_expected_compatibility(
    queries: Sequence[BenchmarkQuery],
    expected_results: Mapping[str, Mapping[str, float]],
) -> None:
    query_ids = {query.query_id for query in queries}
    result_ids = set(expected_results)
    missing = query_ids - result_ids
    extra = result_ids - query_ids
    if missing:
        raise ValueError(f"expected_results missing query ids: {sorted(missing)}")
    if extra:
        raise ValueError(f"expected_results has unknown query ids: {sorted(extra)}")


def _relevance_scores(
    *,
    query_id: str,
    retrieved_ids: Sequence[str],
    expected_results: Mapping[str, Mapping[str, float]],
    cutoff: int,
) -> list[float]:
    grades = expected_results.get(query_id, {})
    scores = [float(grades.get(doc_id, 0.0)) for doc_id in retrieved_ids[:cutoff]]
    while len(scores) < cutoff:
        scores.append(0.0)
    return scores


def _output_paths(config: DenseEmbeddingABConfig) -> DenseEmbeddingABPaths:
    return DenseEmbeddingABPaths(
        csv_path=config.output_dir / DEFAULT_CSV_FILENAME,
        json_path=config.output_dir / DEFAULT_JSON_FILENAME,
        markdown_path=config.output_dir / DEFAULT_MARKDOWN_FILENAME,
        adr_path=config.adr_path,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_result_to_dict(result: DenseProfileResult) -> dict[str, object]:
    return asdict(result)


def _decision_to_dict(decision: PromotionDecision) -> dict[str, object]:
    return {
        "promote_qwen3_dense": decision.promote_qwen3_dense,
        "accepted_profile": decision.accepted_profile,
        "candidate_profile": decision.candidate_profile,
        "reason": decision.reason,
        "thresholds": asdict(decision.thresholds),
    }


def _row_to_dict(row: ProfileEvaluationRow) -> dict[str, object]:
    return {
        "profile_id": row.profile_id,
        "query_id": row.query_id,
        "category": row.category,
        "status": row.status,
        "precision_at_5": row.precision_at_5,
        "recall_at_10": row.recall_at_10,
        "mrr": row.mrr,
        "ndcg_at_5": row.ndcg_at_5,
        "embedding_latency_ms": row.embedding_latency_ms,
        "query_latency_ms": row.query_latency_ms,
        "ingest_latency_ms": row.ingest_latency_ms,
        "total_latency_ms": row.total_latency_ms,
        "top_k": row.top_k,
        "hit_ids": list(row.hit_ids),
        "hit_scores": list(row.hit_scores),
        "retrieved_ids": list(row.retrieved_ids),
        "scores": list(row.scores),
        "error_type": row.error_type,
        "error_message": row.error_message,
    }


def _assert_safe_output(value: object) -> None:
    forbidden = {
        "answer",
        "chunk_text",
        "document_text",
        "embedding",
        "embeddings",
        "payload",
        "prompt",
        "qdrant_payload",
        "raw_document",
        "text",
        "vector",
        "vectors",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key in forbidden:
                raise ValueError(f"sensitive output key is forbidden: {key}")
            _assert_safe_output(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_output(item)


def _relative_gain(candidate: float, baseline: float) -> float:
    if abs(baseline) <= EPSILON:
        if candidate <= EPSILON:
            return 0.0
        return math.inf
    return (candidate - baseline) / baseline


def _latency_multiplier(candidate: float, baseline: float) -> float:
    if abs(baseline) <= EPSILON:
        if candidate <= EPSILON:
            return 1.0
        return math.inf
    return candidate / baseline


def _quality_row(label: str, baseline: float, candidate: float) -> str:
    return (
        f"| {label} | {_score(baseline)} | {_score(candidate)} | "
        f"{_format_percent_delta(candidate, baseline)} | "
        f"{_winner_higher('Nomic', 'Qwen3-8B', baseline, candidate)} |"
    )


def _latency_row(label: str, baseline: float, candidate: float) -> str:
    multiplier = _latency_multiplier(candidate, baseline)
    return (
        f"| {label} | {_ms(baseline)} | {_ms(candidate)} | "
        f"{_format_multiplier(multiplier)} | "
        f"{_winner_lower('Nomic', 'Qwen3-8B', baseline, candidate)} |"
    )


def _winner_higher(
    baseline_label: str,
    candidate_label: str,
    baseline: float,
    candidate: float,
) -> str:
    if candidate > baseline:
        return candidate_label
    if baseline > candidate:
        return baseline_label
    return "Empate"


def _winner_lower(
    baseline_label: str,
    candidate_label: str,
    baseline: float,
    candidate: float,
) -> str:
    if candidate < baseline:
        return candidate_label
    if baseline < candidate:
        return baseline_label
    return "Empate"


def _format_percent_delta(candidate: float, baseline: float) -> str:
    gain = _relative_gain(candidate, baseline)
    if math.isinf(gain):
        return "+inf"
    return f"{gain * 100.0:+.1f}%"


def _format_ratio(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.3f}"


def _format_multiplier(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.1f}x"


def _score(value: float) -> str:
    return f"{value:.3f}"


def _ms(value: float) -> str:
    return f"{value:.1f}"


def _latency_axis_max(
    baseline: DenseProfileResult,
    candidate: DenseProfileResult,
) -> str:
    max_value = max(
        baseline.query_latency_p95_ms,
        baseline.embedding_latency_p95_ms,
        candidate.query_latency_p95_ms,
        candidate.embedding_latency_p95_ms,
        1.0,
    )
    return str(int(math.ceil(max_value * 1.2)))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DenseEmbeddingABConfig",
    "DenseEmbeddingABPaths",
    "DenseEmbeddingABResult",
    "DenseEmbeddingBenchmark",
    "DenseProfileQueryResult",
    "DenseProfileResult",
    "DenseProfileRun",
    "DenseProfileRunner",
    "ProfileEvaluationRow",
    "PromotionDecision",
    "PromotionThresholds",
    "compare_dense_embeddings",
    "decide_promotion",
    "ensure_fair_comparison",
    "evaluate_profile_run",
    "load_benchmark",
    "main",
    "render_markdown_report",
    "summarize_profile_run",
    "write_adr",
    "write_csv",
    "write_json",
    "write_markdown",
]
