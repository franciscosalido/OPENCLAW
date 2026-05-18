"""Unit tests for the PR-04C dense embedding A/B benchmark."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from evaluation.compare_dense_embeddings import (
    DenseEmbeddingABConfig,
    DenseEmbeddingBenchmark,
    DenseProfileQueryResult,
    DenseProfileRun,
    PromotionThresholds,
    compare_dense_embeddings,
    decide_promotion,
    ensure_fair_comparison,
)


class FakeProfileRunner:
    def __init__(
        self,
        *,
        dimensions: int,
        collection_size: int,
        corpus_hash: str,
        results: Mapping[str, tuple[tuple[str, ...], tuple[float, ...]]],
    ) -> None:
        self.dimensions = dimensions
        self.collection_size = collection_size
        self.corpus_hash = corpus_hash
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def run(
        self,
        benchmark: DenseEmbeddingBenchmark,
        *,
        profile_id: str,
        top_k: int,
    ) -> DenseProfileRun:
        self.calls.append((profile_id, top_k))
        rows: list[DenseProfileQueryResult] = []
        for index, query in enumerate(benchmark.queries, start=1):
            retrieved_ids, scores = self.results[query.query_id]
            rows.append(
                DenseProfileQueryResult(
                    query_id=query.query_id,
                    retrieved_ids=retrieved_ids,
                    scores=scores,
                    embedding_latency_ms=10.0 * index
                    if "nomic" in profile_id
                    else 20.0 * index,
                    query_latency_ms=5.0 * index
                    if "nomic" in profile_id
                    else 8.0 * index,
                    ingest_latency_ms=2.0 * index
                    if "nomic" in profile_id
                    else 3.0 * index,
                )
            )
        return DenseProfileRun(
            profile_id=profile_id,
            dimensions=self.dimensions,
            collection_size=self.collection_size,
            benchmark_hash=benchmark.benchmark_hash,
            corpus_hash=self.corpus_hash,
            query_results=tuple(rows),
        )


class DenseEmbeddingABTests(unittest.TestCase):
    def test_compare_writes_csv_json_markdown_and_adr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, expected_path = _write_inputs(root)
            output_dir = root / "results"
            adr_path = root / "adr.md"

            result = compare_dense_embeddings(
                baseline_runner=FakeProfileRunner(
                    dimensions=768,
                    collection_size=2,
                    corpus_hash="corpus-a",
                    results={
                        "Q_001": (("doc_x", "doc_a"), (0.8, 0.7)),
                        "Q_002": (("doc_y", "doc_c"), (0.6, 0.5)),
                    },
                ),
                candidate_runner=FakeProfileRunner(
                    dimensions=4096,
                    collection_size=2,
                    corpus_hash="corpus-a",
                    results={
                        "Q_001": (("doc_a", "doc_b"), (0.9, 0.8)),
                        "Q_002": (("doc_c", "doc_y"), (0.95, 0.1)),
                    },
                ),
                config=DenseEmbeddingABConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=output_dir,
                    adr_path=adr_path,
                    top_k=20,
                ),
                thresholds=PromotionThresholds(
                    max_query_p95_latency_multiplier=10.0,
                    max_embedding_p95_latency_multiplier=10.0,
                ),
            )

            self.assertTrue(result.decision.promote_qwen3_dense)
            self.assertEqual(result.decision.accepted_profile, "qwen3_dense_8b_v1")
            self.assertTrue(result.paths.csv_path.exists())
            self.assertTrue(result.paths.json_path.exists())
            self.assertTrue(result.paths.markdown_path.exists())
            self.assertTrue(result.paths.adr_path.exists())

            with result.paths.csv_path.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["profile_id"], "nomic_dense_v1")
            self.assertNotIn("query alpha", result.paths.csv_path.read_text(encoding="utf-8"))

            payload = _json_mapping(result.paths.json_path)
            self.assertIn("decision_gate", payload)
            self.assertIn("profiles", payload)
            decision = _mapping(payload["decision_gate"])
            self.assertEqual(decision["accepted_profile"], "qwen3_dense_8b_v1")

            markdown = result.paths.markdown_path.read_text(encoding="utf-8")
            self.assertIn("xychart-beta", markdown)
            self.assertIn("Mais preciso", markdown)
            self.assertIn("Mais rápido", markdown)
            self.assertIn("promote_qwen3_dense: true", markdown)

    def test_decision_rejects_candidate_when_latency_is_too_high(self) -> None:
        nomic = _profile_result(
            profile_id="nomic_dense_v1",
            recall=0.50,
            ndcg=0.50,
            query_p95=100.0,
            embedding_p95=50.0,
        )
        qwen3 = _profile_result(
            profile_id="qwen3_dense_8b_v1",
            recall=0.80,
            ndcg=0.80,
            query_p95=1000.0,
            embedding_p95=2000.0,
        )

        decision = decide_promotion(nomic, qwen3)

        self.assertFalse(decision.promote_qwen3_dense)
        self.assertEqual(decision.accepted_profile, "nomic_dense_v1")
        self.assertIn("did not meet", decision.reason)

    def test_fairness_guard_rejects_benchmark_hash_mismatch(self) -> None:
        nomic = _profile_result(profile_id="nomic_dense_v1", benchmark_hash="a")
        qwen3 = _profile_result(profile_id="qwen3_dense_8b_v1", benchmark_hash="b")

        with self.assertRaisesRegex(ValueError, "identical benchmark queries"):
            ensure_fair_comparison(nomic, qwen3)

    def test_fairness_guard_rejects_corpus_hash_mismatch(self) -> None:
        nomic = _profile_result(profile_id="nomic_dense_v1", corpus_hash="a")
        qwen3 = _profile_result(profile_id="qwen3_dense_8b_v1", corpus_hash="b")

        with self.assertRaisesRegex(ValueError, "identical corpus snapshot"):
            ensure_fair_comparison(nomic, qwen3)


def _write_inputs(root: Path) -> tuple[Path, Path]:
    benchmark_path = root / "benchmark_queries.yaml"
    expected_path = root / "expected_results.yaml"
    benchmark_path.write_text(
        """
- id: Q_001
  query: "query alpha"
  category: alpha
  expected_doc_ids: ["doc_a", "doc_b"]
- id: Q_002
  query: "query beta"
  category: beta
  expected_doc_ids: ["doc_c"]
""".lstrip(),
        encoding="utf-8",
    )
    expected_path.write_text(
        """
Q_001:
  doc_a: 2
  doc_b: 1
Q_002:
  doc_c: 2
""".lstrip(),
        encoding="utf-8",
    )
    return benchmark_path, expected_path


def _profile_result(
    *,
    profile_id: str,
    recall: float = 0.5,
    ndcg: float = 0.5,
    query_p95: float = 100.0,
    embedding_p95: float = 50.0,
    benchmark_hash: str = "benchmark",
    corpus_hash: str = "corpus",
) -> Any:
    from evaluation.compare_dense_embeddings import DenseProfileResult

    return DenseProfileResult(
        profile_id=profile_id,
        precision_at_5=0.5,
        recall_at_10=recall,
        mrr=0.5,
        ndcg_at_5=ndcg,
        query_latency_p50_ms=query_p95 / 2.0,
        query_latency_p95_ms=query_p95,
        embedding_latency_p50_ms=embedding_p95 / 2.0,
        embedding_latency_p95_ms=embedding_p95,
        ingest_latency_p50_ms=10.0,
        ingest_latency_p95_ms=20.0,
        dimensions=768 if "nomic" in profile_id else 4096,
        collection_size=2,
        benchmark_hash=benchmark_hash,
        corpus_hash=corpus_hash,
    )


def _json_mapping(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("expected JSON object")
    return cast(dict[str, Any], raw)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError("expected mapping")
    return cast(dict[str, Any], value)


if __name__ == "__main__":
    unittest.main()
