"""Dense-only baseline runner for Sprint RAG-1A PR-03.

This module is a thin orchestration layer. It reads the versioned benchmark,
calls an injected dense retriever, computes metrics through the public
``evaluation`` package, and writes local result artifacts. It must not mutate
Qdrant collections, schemas, benchmark files, or metric implementations.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

import yaml
from loguru import logger

from evaluation import (
    latency_percentiles,
    mean_precision_at_k,
    mean_recall_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


RUNNER_VERSION = "rag-1a-pr03"
DEFAULT_TOP_K = 20
DEFAULT_CUTOFF_PRECISION = 5
DEFAULT_CUTOFF_RECALL = 10
DEFAULT_CUTOFF_NDCG = 5
DEFAULT_COLLECTION_NAME = "openclaw_financial"
DEFAULT_RESULTS_DIR = Path("evaluation") / "results"
DEFAULT_BENCHMARK_FILE = Path("evaluation") / "benchmark_queries.yaml"
DEFAULT_EXPECTED_RESULTS_FILE = Path("evaluation") / "expected_results.yaml"
DEFAULT_JSONL_FILENAME = "dense_baseline.jsonl"
DEFAULT_JSON_FILENAME = "dense_baseline.json"
DEFAULT_CSV_FILENAME = "dense_baseline.csv"
ENV_GIT_COMMIT = "QUIMERA_GIT_COMMIT"
RANKING_METRIC_NOTE = "mrr is the official RAG-1A ranking metric; map_at_k is null"
SENSITIVE_OUTPUT_KEYS = frozenset(
    {
        "answer",
        "chunk_text",
        "document_text",
        "embedding",
        "embeddings",
        "payload",
        "prompt",
        "qdrant_payload",
        "raw_document",
        "text_chunk",
        "vector",
        "vectors",
    }
)


@dataclass(frozen=True)
class ScoredDocument:
    """A metadata-only dense retrieval result."""

    doc_id: str
    score: float


class DenseRetriever(Protocol):
    """Read-only dense retriever contract used by the baseline runner."""

    def retrieve(self, query: str, top_k: int) -> Sequence[ScoredDocument]:
        """Return ranked scored document IDs without mutating collections."""
        ...


@dataclass(frozen=True)
class RetrieverMetadata:
    """Safe retriever provenance for the baseline report."""

    type: str
    collection_name: str
    embedding_model: str
    embedding_provider: str

    def to_json_dict(self) -> dict[str, str]:
        """Return JSON-serializable retriever metadata."""

        return {
            "type": self.type,
            "collection_name": self.collection_name,
            "embedding_model": self.embedding_model,
            "embedding_provider": self.embedding_provider,
        }


@dataclass(frozen=True)
class BenchmarkQuery:
    """One validated benchmark query row."""

    query_id: str
    query: str
    category: str
    expected_doc_ids: tuple[str, ...]


@dataclass(frozen=True)
class DenseBaselineConfig:
    """Runtime configuration for a dense-only baseline run."""

    benchmark_file: Path = DEFAULT_BENCHMARK_FILE
    expected_results_file: Path = DEFAULT_EXPECTED_RESULTS_FILE
    output_dir: Path = DEFAULT_RESULTS_DIR
    top_k: int = DEFAULT_TOP_K
    cutoff_precision: int = DEFAULT_CUTOFF_PRECISION
    cutoff_recall: int = DEFAULT_CUTOFF_RECALL
    cutoff_ndcg: int = DEFAULT_CUTOFF_NDCG
    include_cold_start: bool = False
    run_id: str = ""

    def normalized(self) -> DenseBaselineConfig:
        """Return a normalized copy with a run id and validated cutoffs."""

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
        run_id = self.run_id or uuid4().hex
        return DenseBaselineConfig(
            benchmark_file=self.benchmark_file,
            expected_results_file=self.expected_results_file,
            output_dir=self.output_dir,
            top_k=self.top_k,
            cutoff_precision=self.cutoff_precision,
            cutoff_recall=self.cutoff_recall,
            cutoff_ndcg=self.cutoff_ndcg,
            include_cold_start=self.include_cold_start,
            run_id=run_id,
        )


@dataclass(frozen=True)
class DenseBaselinePaths:
    """Output paths written by the baseline runner."""

    jsonl_path: Path
    json_path: Path
    csv_path: Path


@dataclass(frozen=True)
class DenseBaselineResult:
    """Final dense baseline result returned to tests and CLI."""

    metadata: dict[str, object]
    aggregate: dict[str, object]
    results: list[dict[str, object]]
    paths: DenseBaselinePaths


@dataclass(frozen=True)
class DryRunResult:
    """Validation summary returned by ``--dry-run``."""

    metadata: dict[str, object]
    total_queries: int
    categories: tuple[str, ...]


class BackendDenseRetriever:
    """Adapter from the existing async RAG retriever to the PR-03 sync protocol."""

    def __init__(
        self,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        from backend.rag.embedder_factory import create_rag_embedder, load_rag_embedding_config
        from backend.rag.qdrant_store import QdrantVectorStore
        from backend.rag.retriever import DEFAULT_SCORE_THRESHOLD, Retriever

        embedding_config = load_rag_embedding_config()
        self.metadata = RetrieverMetadata(
            type="backend.rag.retriever.Retriever",
            collection_name=collection_name,
            embedding_model=embedding_config.embedding_alias,
            embedding_provider=embedding_config.active_backend,
        )
        self._store = QdrantVectorStore(collection_name=collection_name)
        self._retriever = Retriever(
            embedder=create_rag_embedder(),
            store=self._store,
            top_k=top_k,
            score_threshold=DEFAULT_SCORE_THRESHOLD,
        )

    def retrieve(self, query: str, top_k: int) -> Sequence[ScoredDocument]:
        """Retrieve ranked IDs using the existing dense vector path."""

        chunks = asyncio.run(self._retriever.retrieve(query, top_k=top_k))
        return tuple(
            ScoredDocument(doc_id=chunk.doc_id, score=float(chunk.score))
            for chunk in chunks
        )

    def close(self) -> None:
        """Close owned Qdrant resources."""

        self._store.close()


def create_dense_retriever_from_config(
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    top_k: int = DEFAULT_TOP_K,
) -> BackendDenseRetriever:
    """Create the production dense retriever without mutating Qdrant state."""

    return BackendDenseRetriever(collection_name=collection_name, top_k=top_k)


def run_dense_baseline(
    *,
    retriever: DenseRetriever,
    config: DenseBaselineConfig,
    retriever_metadata: RetrieverMetadata,
    git_commit: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> DenseBaselineResult:
    """Run the dense-only baseline and write JSONL, JSON and CSV artifacts."""

    active_config = config.normalized()
    queries = load_benchmark_queries(active_config.benchmark_file)
    expected_results = load_expected_results(active_config.expected_results_file)
    metadata = build_metadata(
        config=active_config,
        retriever_metadata=retriever_metadata,
        git_commit=git_commit,
    )

    paths = _output_paths(active_config.output_dir)
    active_config.output_dir.mkdir(parents=True, exist_ok=True)

    with paths.jsonl_path.open("a", encoding="utf-8") as jsonl_file:
        for index, query in enumerate(queries):
            row = _run_one_query(
                query=query,
                expected_results=expected_results,
                retriever=retriever,
                config=active_config,
                cold_start=index == 0,
                clock=clock,
            )
            _assert_safe_output(row)
            jsonl_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            jsonl_file.flush()

    results = _read_jsonl_rows(paths.jsonl_path, run_id=active_config.run_id)
    aggregate = _build_aggregate(
        rows=results,
        include_cold_start=active_config.include_cold_start,
        cutoff_precision=active_config.cutoff_precision,
        cutoff_recall=active_config.cutoff_recall,
    )
    snapshot = {
        "metadata": metadata,
        "aggregate": aggregate,
        "results": results,
    }
    _assert_safe_output(snapshot)
    paths.json_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(paths.csv_path, results)
    return DenseBaselineResult(
        metadata=metadata,
        aggregate=aggregate,
        results=results,
        paths=paths,
    )


def dry_run_dense_baseline(
    *,
    config: DenseBaselineConfig,
    retriever: DenseRetriever,
    retriever_metadata: RetrieverMetadata,
    git_commit: str | None = None,
) -> DryRunResult:
    """Validate inputs and retriever shape without executing retrieval or writing files."""

    active_config = config.normalized()
    queries = load_benchmark_queries(active_config.benchmark_file)
    expected_results = load_expected_results(active_config.expected_results_file)
    _validate_expected_compatibility(queries, expected_results)
    _validate_retriever_shape(retriever)
    categories = tuple(sorted({query.category for query in queries}))
    metadata = build_metadata(
        config=active_config,
        retriever_metadata=retriever_metadata,
        git_commit=git_commit,
    )
    return DryRunResult(
        metadata=metadata,
        total_queries=len(queries),
        categories=categories,
    )


def load_benchmark_queries(path: Path) -> list[BenchmarkQuery]:
    """Load benchmark queries from YAML using the PR-01 schema."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("benchmark_queries.yaml must contain a list")

    queries: list[BenchmarkQuery] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("each benchmark query must be a mapping")
        query_id = _required_string(item, "id")
        query_text = _required_string(item, "query")
        category = _required_string(item, "category")
        expected_doc_ids = _required_string_tuple(item, "expected_doc_ids")
        queries.append(
            BenchmarkQuery(
                query_id=query_id,
                query=query_text,
                category=category,
                expected_doc_ids=expected_doc_ids,
            )
        )
    if not queries:
        raise ValueError("benchmark query list must not be empty")
    return queries


def load_expected_results(path: Path) -> dict[str, dict[str, float]]:
    """Load expected relevance grades from YAML."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("expected_results.yaml must contain a mapping")
    parsed: dict[str, dict[str, float]] = {}
    for query_id, grades in raw.items():
        if not isinstance(query_id, str):
            raise ValueError("expected_results query ids must be strings")
        if not isinstance(grades, Mapping):
            raise ValueError(f"expected_results for {query_id} must be a mapping")
        parsed[query_id] = {}
        for doc_id, grade in grades.items():
            if not isinstance(doc_id, str):
                raise ValueError(f"doc_id for {query_id} must be a string")
            if isinstance(grade, bool) or not isinstance(grade, (int, float)):
                raise ValueError(f"relevance grade for {query_id}/{doc_id} must be numeric")
            if float(grade) < 0.0:
                raise ValueError(f"relevance grade for {query_id}/{doc_id} cannot be negative")
            parsed[query_id][doc_id] = float(grade)
    return parsed


def build_metadata(
    *,
    config: DenseBaselineConfig,
    retriever_metadata: RetrieverMetadata,
    git_commit: str | None = None,
) -> dict[str, object]:
    """Build safe run metadata with benchmark provenance."""

    return {
        "runner_version": RUNNER_VERSION,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit or _current_git_commit(),
        "benchmark_file": str(config.benchmark_file),
        "benchmark_sha256": _sha256_file(config.benchmark_file),
        "expected_results_file": str(config.expected_results_file),
        "expected_results_sha256": _sha256_file(config.expected_results_file),
        "retriever": retriever_metadata.to_json_dict(),
        "top_k": config.top_k,
        "cutoff_precision": config.cutoff_precision,
        "cutoff_recall": config.cutoff_recall,
        "cutoff_ndcg": config.cutoff_ndcg,
        "include_cold_start": config.include_cold_start,
        "ranking_metric": "mrr",
        "ranking_metric_note": RANKING_METRIC_NOTE,
        "map_at_k": None,
    }


def _run_one_query(
    *,
    query: BenchmarkQuery,
    expected_results: Mapping[str, Mapping[str, float]],
    retriever: DenseRetriever,
    config: DenseBaselineConfig,
    cold_start: bool,
    clock: Callable[[], float],
) -> dict[str, object]:
    start = clock()
    retrieved_ids: list[str] = []
    scores: list[float] = []
    status = "ok"
    error_type: str | None = None
    error_message: str | None = None
    metrics = _zero_metrics()

    try:
        expected_ids = frozenset(query.expected_doc_ids)
        if not expected_ids:
            raise ValueError("expected_ids_empty")
        scored_documents = retriever.retrieve(query.query, config.top_k)
        retrieved_ids = [doc.doc_id for doc in scored_documents]
        scores = [float(doc.score) for doc in scored_documents]
        relevance_scores = _relevance_scores(
            query_id=query.query_id,
            retrieved_ids=retrieved_ids,
            expected_results=expected_results,
            cutoff=config.cutoff_ndcg,
        )
        metrics = {
            "precision_at_5": precision_at_k(
                retrieved_ids,
                expected_ids,
                config.cutoff_precision,
            ),
            "recall_at_10": recall_at_k(
                retrieved_ids,
                expected_ids,
                config.cutoff_recall,
            ),
            "reciprocal_rank": reciprocal_rank(retrieved_ids, expected_ids),
            "ndcg_at_5": ndcg_at_k(relevance_scores, config.cutoff_ndcg),
        }
    except Exception as exc:
        status = "error"
        error_type = exc.__class__.__name__
        error_message = _sanitize_error_message(str(exc))

    latency_ms = (clock() - start) * 1000.0
    return {
        "run_id": config.run_id,
        "query_id": query.query_id,
        "query": query.query,
        "category": query.category,
        "expected_doc_ids": list(query.expected_doc_ids),
        "retrieved_ids": retrieved_ids,
        "scores": scores,
        "latency_ms": latency_ms,
        "cold_start": cold_start,
        "metrics": metrics,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
    }


def _zero_metrics() -> dict[str, float]:
    return {
        "precision_at_5": 0.0,
        "recall_at_10": 0.0,
        "reciprocal_rank": 0.0,
        "ndcg_at_5": 0.0,
    }


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


def _build_aggregate(
    *,
    rows: Sequence[Mapping[str, object]],
    include_cold_start: bool,
    cutoff_precision: int,
    cutoff_recall: int,
) -> dict[str, object]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    global_aggregate = _aggregate_rows(
        ok_rows,
        include_cold_start=include_cold_start,
        cutoff_precision=cutoff_precision,
        cutoff_recall=cutoff_recall,
    )

    rows_by_category: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in ok_rows:
        category = row.get("category")
        if isinstance(category, str):
            rows_by_category[category].append(row)

    by_category = {
        category: _aggregate_rows(
            category_rows,
            include_cold_start=include_cold_start,
            cutoff_precision=cutoff_precision,
            cutoff_recall=cutoff_recall,
        )
        for category, category_rows in sorted(rows_by_category.items())
    }

    return {
        "global": global_aggregate,
        "by_category": by_category,
    }


def _aggregate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    include_cold_start: bool,
    cutoff_precision: int,
    cutoff_recall: int,
) -> dict[str, object]:
    if not rows:
        return {
            "evaluated_queries": 0,
            "mean_precision_at_5": 0.0,
            "mean_recall_at_10": 0.0,
            "mean_reciprocal_rank": 0.0,
            "mean_ndcg_at_5": 0.0,
            "latency_ms": {50: 0.0, 95: 0.0, 99: 0.0},
        }

    precision_recall_inputs: list[tuple[Sequence[str], frozenset[str]]] = []
    rr_scores: list[float] = []
    ndcg_scores: list[float] = []
    latencies: list[float] = []
    for row in rows:
        retrieved_ids = _string_list(row.get("retrieved_ids"))
        expected_doc_ids = frozenset(_string_list(row.get("expected_doc_ids")))
        precision_recall_inputs.append((retrieved_ids, expected_doc_ids))
        metrics = _mapping_value(row.get("metrics"))
        rr_scores.append(_float_metric(metrics, "reciprocal_rank"))
        ndcg_scores.append(_float_metric(metrics, "ndcg_at_5"))
        if include_cold_start or row.get("cold_start") is not True:
            latencies.append(_float_value(row.get("latency_ms"), "latency_ms"))

    latency_output = (
        latency_percentiles(latencies, (50, 95, 99))
        if latencies
        else {50: 0.0, 95: 0.0, 99: 0.0}
    )
    return {
        "evaluated_queries": len(rows),
        "mean_precision_at_5": mean_precision_at_k(
            precision_recall_inputs,
            cutoff_precision,
        ),
        "mean_recall_at_10": mean_recall_at_k(
            precision_recall_inputs,
            cutoff_recall,
        ),
        "mean_reciprocal_rank": mean_reciprocal_rank(rr_scores),
        "mean_ndcg_at_5": sum(ndcg_scores) / float(len(ndcg_scores)),
        "latency_ms": latency_output,
    }


def _read_jsonl_rows(path: Path, *, run_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError("JSONL row must be an object")
        row = cast(dict[str, object], raw)
        if row.get("run_id") == run_id:
            rows.append(row)
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fieldnames = [
        "run_id",
        "query_id",
        "query",
        "category",
        "status",
        "error_type",
        "error_message",
        "cold_start",
        "latency_ms",
        "retrieved_ids",
        "scores",
        "precision_at_5",
        "recall_at_10",
        "reciprocal_rank",
        "ndcg_at_5",
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            metrics = _mapping_value(row.get("metrics"))
            writer.writerow(
                {
                    "run_id": str(row.get("run_id", "")),
                    "query_id": str(row.get("query_id", "")),
                    "query": str(row.get("query", "")),
                    "category": str(row.get("category", "")),
                    "status": str(row.get("status", "")),
                    "error_type": _csv_optional(row.get("error_type")),
                    "error_message": _csv_optional(row.get("error_message")),
                    "cold_start": str(bool(row.get("cold_start"))),
                    "latency_ms": str(row.get("latency_ms", "")),
                    "retrieved_ids": "|".join(_string_list(row.get("retrieved_ids"))),
                    "scores": "|".join(str(score) for score in _float_list(row.get("scores"))),
                    "precision_at_5": str(_float_metric(metrics, "precision_at_5")),
                    "recall_at_10": str(_float_metric(metrics, "recall_at_10")),
                    "reciprocal_rank": str(_float_metric(metrics, "reciprocal_rank")),
                    "ndcg_at_5": str(_float_metric(metrics, "ndcg_at_5")),
                }
            )


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
    empty_expected = [query.query_id for query in queries if not query.expected_doc_ids]
    if empty_expected:
        raise ValueError(f"queries without expected_doc_ids: {empty_expected}")


def _validate_retriever_shape(retriever: DenseRetriever) -> None:
    retrieve = getattr(retriever, "retrieve", None)
    if not callable(retrieve):
        raise TypeError("retriever must expose callable retrieve(query, top_k)")


def _output_paths(output_dir: Path) -> DenseBaselinePaths:
    return DenseBaselinePaths(
        jsonl_path=output_dir / DEFAULT_JSONL_FILENAME,
        json_path=output_dir / DEFAULT_JSON_FILENAME,
        csv_path=output_dir / DEFAULT_CSV_FILENAME,
    )


def _required_string(data: Mapping[object, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _required_string_tuple(data: Mapping[object, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} entries must be strings")
        values.append(item.strip())
    return tuple(values)


def _mapping_value(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping value")
    return cast(Mapping[str, object], value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("expected list value")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("expected string list")
        strings.append(item)
    return strings


def _float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        raise ValueError("expected list value")
    floats: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("expected numeric list")
        floats.append(float(item))
    return floats


def _float_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _float_metric(metrics: Mapping[str, object], key: str) -> float:
    return _float_value(metrics.get(key), key)


def _csv_optional(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_git_commit() -> str:
    env_value = os.environ.get(ENV_GIT_COMMIT)
    if env_value:
        return env_value
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _sanitize_error_message(message: str) -> str:
    clean = " ".join(message.split())
    return clean[:240]


def _assert_safe_output(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key in SENSITIVE_OUTPUT_KEYS:
                raise ValueError(f"sensitive output key is forbidden: {key}")
            _assert_safe_output(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_output(item)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Run the RAG-1A dense-only baseline.")
    parser.add_argument("--benchmark-file", type=Path, default=DEFAULT_BENCHMARK_FILE)
    parser.add_argument(
        "--expected-results-file",
        type=Path,
        default=DEFAULT_EXPECTED_RESULTS_FILE,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--collection-name", default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-cold-start", action="store_true")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    retriever: DenseRetriever | None = None,
    retriever_metadata: RetrieverMetadata | None = None,
) -> int:
    """Run the dense-only baseline CLI.

    The CLI is read-only by contract: it calls only the retriever's read path
    and never invokes collection mutation methods such as upsert, delete,
    truncate, recreate or compact.
    """

    args = parse_args(argv)
    config = DenseBaselineConfig(
        benchmark_file=args.benchmark_file,
        expected_results_file=args.expected_results_file,
        output_dir=args.output_dir,
        top_k=args.top_k,
        include_cold_start=args.include_cold_start,
    )
    metadata = retriever_metadata or RetrieverMetadata(
        type="dry_run" if args.dry_run else "backend.rag.retriever.Retriever",
        collection_name=str(args.collection_name),
        embedding_model="quimera_embed",
        embedding_provider="gateway_litellm",
    )

    active_retriever = retriever
    backend_retriever: BackendDenseRetriever | None = None
    if active_retriever is None and not args.dry_run:
        backend_retriever = create_dense_retriever_from_config(
            collection_name=str(args.collection_name),
            top_k=args.top_k,
        )
        active_retriever = backend_retriever
        metadata = backend_retriever.metadata
    if active_retriever is None:
        active_retriever = _DryRunRetriever()

    try:
        if args.dry_run:
            dry_result = dry_run_dense_baseline(
                config=config,
                retriever=active_retriever,
                retriever_metadata=metadata,
            )
            logger.info(
                "dense baseline dry-run ok | queries={} categories={}",
                dry_result.total_queries,
                dry_result.categories,
            )
            return 0

        baseline_result = run_dense_baseline(
            retriever=active_retriever,
            config=config,
            retriever_metadata=metadata,
        )
        logger.info(
            "dense baseline complete | json={} csv={}",
            baseline_result.paths.json_path,
            baseline_result.paths.csv_path,
        )
        return 0
    finally:
        if backend_retriever is not None:
            backend_retriever.close()


class _DryRunRetriever:
    def retrieve(self, query: str, top_k: int) -> Sequence[ScoredDocument]:
        del query, top_k
        return ()


if __name__ == "__main__":
    raise SystemExit(main())
