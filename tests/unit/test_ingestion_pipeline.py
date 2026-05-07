from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.ingestion.pipeline import IngestionOptions, run_ingestion
from backend.ingestion.report import FORBIDDEN_REPORT_KEYS, assert_report_is_sanitized
from backend.rag.qdrant_store import VectorStoreChunk


def _doc_yaml(
    *,
    source_id: str,
    doc_id: str,
    path: str,
    contains_pii: bool = False,
    curation_status: str = "approved",
    enabled: bool = True,
) -> str:
    return f"""
  - source_id: {source_id}
    doc_id: {doc_id}
    origin_path: {path}
    source_type: md
    domain: macroeconomia
    language: pt-BR
    license: synthetic-internal
    contains_pii: {str(contains_pii).lower()}
    curation_status: {curation_status}
    ingestion_policy: financial
    enabled: {str(enabled).lower()}
"""


def _write_manifest(root: Path, docs_yaml: str) -> Path:
    manifest_path = root / "manifest.yaml"
    manifest_path.write_text(f"version: 1\ndocuments:{docs_yaml}", encoding="utf-8")
    return manifest_path


class IngestionPipelineTests(unittest.TestCase):
    def test_contains_pii_true_rejected_before_parser_called(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = _write_manifest(
                root,
                _doc_yaml(
                    source_id="synth-test-001",
                    doc_id="doc_pii",
                    path="docs/pii.md",
                    contains_pii=True,
                ),
            )

            with patch("backend.ingestion.pipeline.parse_document") as parser:
                result = run_ingestion(IngestionOptions(manifest_path=manifest))

        parser.assert_not_called()
        per_document = result.report["per_document"]
        self.assertIsInstance(per_document, list)
        self.assertEqual(per_document[0]["rejection_reason"], "contains_pii_manifest")

    def test_pending_docs_block_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = _write_manifest(
                root,
                _doc_yaml(
                    source_id="synth-test-001",
                    doc_id="doc_pending",
                    path="docs/pending.md",
                    curation_status="pending",
                ),
            )

            with self.assertRaises(ValueError):
                run_ingestion(IngestionOptions(manifest_path=manifest, mode="commit"))

    def test_enabled_false_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = _write_manifest(
                root,
                _doc_yaml(
                    source_id="synth-test-001",
                    doc_id="doc_disabled",
                    path="docs/disabled.md",
                    enabled=False,
                ),
            )

            result = run_ingestion(IngestionOptions(manifest_path=manifest))

        per_document = result.report["per_document"]
        self.assertIsInstance(per_document, list)
        self.assertEqual(per_document[0]["status"], "skipped")
        self.assertEqual(result.report["skipped_documents"], 1)

    def test_dedup_same_bytes_different_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            docs.mkdir()
            (docs / "a.md").write_text("conteudo sintetico duplicado", encoding="utf-8")
            (docs / "b.md").write_text("conteudo sintetico duplicado", encoding="utf-8")
            manifest = _write_manifest(
                root,
                _doc_yaml(source_id="synth-test-001", doc_id="doc_a", path="docs/a.md")
                + _doc_yaml(source_id="synth-test-002", doc_id="doc_b", path="docs/b.md"),
            )

            result = run_ingestion(IngestionOptions(manifest_path=manifest))

        per_document = result.report["per_document"]
        self.assertIsInstance(per_document, list)
        self.assertEqual(per_document[1]["status"], "duplicate")
        self.assertEqual(result.report["duplicate_documents"], 1)

    def test_report_contains_no_forbidden_keys(self) -> None:
        result = run_ingestion(IngestionOptions(manifest_path=Path("data/corpus/manifest.yaml")))

        assert_report_is_sanitized(result.report)
        self.assertTrue(FORBIDDEN_REPORT_KEYS.isdisjoint(result.report))

    def test_coverage_and_latency_metrics_for_ten_synthetic_docs(self) -> None:
        result = run_ingestion(IngestionOptions(manifest_path=Path("data/corpus/manifest.yaml")))

        self.assertEqual(result.report["total_documents"], 10)
        self.assertEqual(result.report["chunked_documents"], 10)
        self.assertEqual(result.report["coverage"], 1.0)
        self.assertIn("p50_ingestion_ms", result.report)
        self.assertIn("p95_ingestion_ms", result.report)
        self.assertIsInstance(result.chunks[0], VectorStoreChunk)


if __name__ == "__main__":
    unittest.main()

