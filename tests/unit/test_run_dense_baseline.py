"""Unit tests for the dense-only baseline runner."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from evaluation.run_dense_baseline import (
    DenseBaselineConfig,
    RetrieverMetadata,
    ScoredDocument,
    dry_run_dense_baseline,
    run_dense_baseline,
)


class FakeRetriever:
    def __init__(self, results: dict[str, Sequence[ScoredDocument]]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int) -> Sequence[ScoredDocument]:
        self.calls.append((query, top_k))
        return self.results.get(query, ())


class ExplodingRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, query: str, top_k: int) -> Sequence[ScoredDocument]:
        del query, top_k
        self.calls += 1
        raise AssertionError("dry-run must not call retrieve")


class FakeClock:
    def __init__(self, values: Sequence[float]) -> None:
        self.values = list(values)
        self.index = 0

    def __call__(self) -> float:
        value = self.values[self.index]
        self.index += 1
        return value


class DenseBaselineRunnerTests(unittest.TestCase):
    def test_happy_path_writes_jsonl_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, expected_path = _write_valid_inputs(root)
            output_dir = root / "results"
            retriever = FakeRetriever(
                {
                    "query alpha": (
                        ScoredDocument("doc_a", 0.9),
                        ScoredDocument("doc_x", 0.1),
                    ),
                    "query beta": (
                        ScoredDocument("doc_z", 0.5),
                        ScoredDocument("doc_c", 0.4),
                    ),
                }
            )

            result = run_dense_baseline(
                retriever=retriever,
                retriever_metadata=_metadata(),
                config=DenseBaselineConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=output_dir,
                    include_cold_start=True,
                    run_id="test-run",
                ),
                git_commit="abc123",
                clock=FakeClock((0.0, 0.010, 0.010, 0.030)),
            )

            jsonl_rows = _read_jsonl(result.paths.jsonl_path)
            self.assertEqual(len(jsonl_rows), 2)
            self.assertEqual([row["query_id"] for row in jsonl_rows], ["Q_001", "Q_002"])
            self.assertEqual(result.metadata["runner_version"], "rag-1a-pr03")
            self.assertEqual(result.metadata["git_commit"], "abc123")
            self.assertIn("global", result.aggregate)
            self.assertIn("by_category", result.aggregate)
            self.assertEqual(result.results[0]["status"], "ok")

            snapshot = _read_json(result.paths.json_path)
            self.assertIn("metadata", snapshot)
            self.assertIn("aggregate", snapshot)
            self.assertIn("results", snapshot)
            self.assertIn("alpha", _mapping(snapshot["aggregate"])["by_category"])

            with result.paths.csv_path.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["query_id"], "Q_001")
            self.assertEqual(rows[0]["retrieved_ids"], "doc_a|doc_x")
            self.assertEqual(rows[0]["status"], "ok")

    def test_query_error_is_written_without_interrupting_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path = root / "benchmark_queries.yaml"
            expected_path = root / "expected_results.yaml"
            benchmark_path.write_text(
                """
- id: BAD_001
  query: "query bad"
  category: alpha
  expected_doc_ids: []
- id: Q_002
  query: "query beta"
  category: beta
  expected_doc_ids: ["doc_c"]
""".lstrip(),
                encoding="utf-8",
            )
            expected_path.write_text(
                """
BAD_001: {}
Q_002:
  doc_c: 2
""".lstrip(),
                encoding="utf-8",
            )
            retriever = FakeRetriever(
                {"query beta": (ScoredDocument("doc_c", 0.7),)}
            )

            result = run_dense_baseline(
                retriever=retriever,
                retriever_metadata=_metadata(),
                config=DenseBaselineConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=root / "results",
                    run_id="error-run",
                ),
                git_commit="abc123",
                clock=FakeClock((0.0, 0.001, 0.001, 0.002)),
            )

            rows = _read_jsonl(result.paths.jsonl_path)
            self.assertEqual([row["status"] for row in rows], ["error", "ok"])
            self.assertEqual(rows[0]["error_type"], "ValueError")
            self.assertEqual(retriever.calls, [("query beta", 20)])

    def test_config_rejects_top_k_equal_to_recall_cutoff(self) -> None:
        config = DenseBaselineConfig(top_k=10, cutoff_recall=10)

        with self.assertRaises(ValueError):
            config.normalized()

    def test_dry_run_does_not_call_retrieve_or_write_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, expected_path = _write_valid_inputs(root)
            output_dir = root / "results"
            retriever = ExplodingRetriever()

            result = dry_run_dense_baseline(
                retriever=retriever,
                retriever_metadata=_metadata(),
                config=DenseBaselineConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=output_dir,
                    run_id="dry-run",
                ),
                git_commit="abc123",
            )

            self.assertEqual(result.total_queries, 2)
            self.assertEqual(result.categories, ("alpha", "beta"))
            self.assertEqual(retriever.calls, 0)
            self.assertFalse((output_dir / "dense_baseline.jsonl").exists())
            self.assertFalse((output_dir / "dense_baseline.json").exists())
            self.assertFalse((output_dir / "dense_baseline.csv").exists())

    def test_cold_start_is_excluded_from_latency_percentiles_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path = root / "benchmark_queries.yaml"
            expected_path = root / "expected_results.yaml"
            benchmark_path.write_text(
                """
- id: Q_001
  query: "query one"
  category: alpha
  expected_doc_ids: ["doc_a"]
- id: Q_002
  query: "query two"
  category: alpha
  expected_doc_ids: ["doc_b"]
- id: Q_003
  query: "query three"
  category: alpha
  expected_doc_ids: ["doc_c"]
""".lstrip(),
                encoding="utf-8",
            )
            expected_path.write_text(
                """
Q_001:
  doc_a: 2
Q_002:
  doc_b: 2
Q_003:
  doc_c: 2
""".lstrip(),
                encoding="utf-8",
            )
            retriever = FakeRetriever(
                {
                    "query one": (ScoredDocument("doc_a", 0.9),),
                    "query two": (ScoredDocument("doc_b", 0.8),),
                    "query three": (ScoredDocument("doc_c", 0.7),),
                }
            )

            result = run_dense_baseline(
                retriever=retriever,
                retriever_metadata=_metadata(),
                config=DenseBaselineConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=root / "results",
                    include_cold_start=False,
                    run_id="latency-run",
                ),
                git_commit="abc123",
                clock=FakeClock((0.0, 0.100, 0.100, 0.300, 0.300, 0.600)),
            )

            latency = cast(
                dict[int, float],
                _mapping(_mapping(result.aggregate["global"])["latency_ms"]),
            )
            self.assertEqual(latency[50], 250.0)
            self.assertEqual(latency[95], 295.0)
            self.assertEqual(latency[99], 299.0)
            rows = result.results
            self.assertEqual([row["cold_start"] for row in rows], [True, False, False])

    def test_outputs_do_not_contain_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, expected_path = _write_valid_inputs(root)
            result = run_dense_baseline(
                retriever=FakeRetriever(
                    {
                        "query alpha": (ScoredDocument("doc_a", 0.9),),
                        "query beta": (ScoredDocument("doc_c", 0.8),),
                    }
                ),
                retriever_metadata=_metadata(),
                config=DenseBaselineConfig(
                    benchmark_file=benchmark_path,
                    expected_results_file=expected_path,
                    output_dir=root / "results",
                    run_id="safe-run",
                ),
                git_commit="abc123",
                clock=FakeClock((0.0, 0.001, 0.001, 0.002)),
            )

            jsonl_rows = _read_jsonl(result.paths.jsonl_path)
            snapshot = _read_json(result.paths.json_path)
            for forbidden in (
                "chunk_text",
                "document_text",
                "embedding",
                "embeddings",
                "payload",
                "prompt",
                "qdrant_payload",
                "raw_document",
                "vector",
                "vectors",
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertFalse(_contains_key(jsonl_rows, forbidden))
                    self.assertFalse(_contains_key(snapshot, forbidden))
            self.assertNotIn(
                "chunk_text",
                result.paths.csv_path.read_text(encoding="utf-8"),
            )


def _write_valid_inputs(root: Path) -> tuple[Path, Path]:
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


def _metadata() -> RetrieverMetadata:
    return RetrieverMetadata(
        type="fake",
        collection_name="test_collection",
        embedding_model="fake-embed",
        embedding_provider="fake-provider",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise AssertionError("JSONL row must be an object")
        rows.append(cast(dict[str, object], raw))
    return rows


def _read_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("JSON snapshot must be an object")
    return cast(dict[str, object], raw)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError("expected mapping")
    return cast(dict[str, Any], value)


def _contains_key(value: object, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        return any(
            key == forbidden_key or _contains_key(nested, forbidden_key)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key(item, forbidden_key) for item in value)
    return False
