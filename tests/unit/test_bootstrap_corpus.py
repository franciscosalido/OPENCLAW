from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from backend.ingestion.bootstrap import (
    BootstrapOptions,
    MappingExistingHashIndex,
    _validate_manifest_for_corpus,
    run_bootstrap,
)
from backend.ingestion.manifest import CorpusManifest
from backend.rag.qdrant_store import VectorStoreChunk
from scripts import bootstrap_corpus


class FakeCommitStore:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[VectorStoreChunk, ...], str | None]] = []

    def commit(
        self,
        chunks: Sequence[VectorStoreChunk],
        *,
        collection: str | None,
    ) -> None:
        self.calls.append((tuple(chunks), collection))


class BootstrapCorpusTests(unittest.TestCase):
    def test_invalid_corpus_arg_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            bootstrap_corpus.main(["--corpus", "unknown"])

    def test_verify_only_and_commit_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            bootstrap_corpus.main(
                ["--corpus", "internal", "--verify-only", "--commit"],
            )

    def test_verify_only_does_not_instantiate_qdrant_commit_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "internal.json"
            with patch("scripts.bootstrap_corpus.QdrantIngestionCommitStore") as store:
                exit_code = bootstrap_corpus.main(
                    [
                        "--corpus",
                        "internal",
                        "--verify-only",
                        "--report-out",
                        str(report_path),
                    ]
                )
            report = cast(dict[str, Any], json.loads(report_path.read_text()))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["mode"], "verify_only")
        store.assert_not_called()

    def test_commit_writes_only_to_mapped_internal_collection_with_fake_store(self) -> None:
        fake_store = FakeCommitStore()

        result = run_bootstrap(
            BootstrapOptions(corpus="internal", mode="commit"),
            commit_store=fake_store,
        )

        self.assertEqual(len(fake_store.calls), 1)
        chunks, collection = fake_store.calls[0]
        self.assertEqual(collection, "openclaw_internal")
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.metadata["corpus"] == "internal" for chunk in chunks))
        self.assertTrue(
            all(chunk.metadata["namespace"] == "openclaw_internal" for chunk in chunks)
        )
        self.assertEqual(result.report["collection_name"], "openclaw_internal")

    def test_commit_writes_only_to_mapped_financial_collection_with_fake_store(self) -> None:
        fake_store = FakeCommitStore()

        result = run_bootstrap(
            BootstrapOptions(corpus="financial", mode="commit"),
            commit_store=fake_store,
        )

        self.assertEqual(len(fake_store.calls), 1)
        chunks, collection = fake_store.calls[0]
        self.assertEqual(collection, "openclaw_financial")
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.metadata["corpus"] == "financial" for chunk in chunks))
        self.assertTrue(
            all(chunk.metadata["namespace"] == "openclaw_financial" for chunk in chunks)
        )
        self.assertEqual(result.report["collection_name"], "openclaw_financial")

    def test_hash_unchanged_marks_skip_unchanged(self) -> None:
        first = run_bootstrap(BootstrapOptions(corpus="financial"))
        per_document = cast(list[dict[str, Any]], first.report["per_document"])
        first_doc = per_document[0]
        existing = MappingExistingHashIndex(
            {
                str(first_doc["doc_id"]): (
                    cast(str | None, first_doc["file_sha256"]),
                    cast(str | None, first_doc["normalized_text_sha256"]),
                )
            }
        )

        second = run_bootstrap(
            BootstrapOptions(corpus="financial"),
            existing_hash_index=existing,
        )

        self.assertEqual(second.report["skipped_unchanged"], 1)
        statuses = {
            document["doc_id"]: document["status"]
            for document in cast(list[dict[str, Any]], second.report["per_document"])
        }
        self.assertEqual(statuses[first_doc["doc_id"]], "skip_unchanged")

    def test_collection_exists_does_not_skip_all_docs_without_hash_match(self) -> None:
        result = run_bootstrap(
            BootstrapOptions(corpus="financial"),
            existing_hash_index=MappingExistingHashIndex({}),
        )

        self.assertEqual(result.report["skipped_unchanged"], 0)
        self.assertEqual(result.report["chunked"], 9)

    def test_report_sanitized_and_query_p95_present_for_both_collections(self) -> None:
        result = run_bootstrap(BootstrapOptions(corpus="internal"))

        self.assertIn("query_dry_run_p95_ms", result.report)
        self.assertIn("internal_query_p95_ms", result.report)
        self.assertIn("financial_query_p95_ms", result.report)
        forbidden = {
            "text",
            "raw_text",
            "normalized_text",
            "chunks",
            "chunk_text",
            "vectors",
            "embeddings",
            "payload",
            "prompt",
            "answer",
            "api_key",
            "authorization",
            "headers",
            "raw_exception",
            "exception_message",
            "traceback",
            "absolute_paths",
            "username",
        }
        self.assertTrue(forbidden.isdisjoint(result.report))

    def test_internal_manifest_rejects_financial_domain(self) -> None:
        manifest = CorpusManifest.model_validate(
            {
                "documents": [
                    _document(
                        ingestion_policy="internal",
                        financial_domain="macroeconomia",
                    )
                ]
            }
        )

        with self.assertRaises(ValueError):
            _validate_manifest_for_corpus(manifest, corpus="internal")

    def test_financial_manifest_requires_financial_domain(self) -> None:
        manifest = CorpusManifest.model_validate(
            {"documents": [_document(ingestion_policy="financial")]}
        )

        with self.assertRaises(ValueError):
            _validate_manifest_for_corpus(manifest, corpus="financial")


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "source_id": "rc-test-source-001",
        "doc_id": "rc_test_doc",
        "origin_path": "docs/rc_test_doc.md",
        "source_type": "md",
        "domain": "internal",
        "language": "pt-BR",
        "license": "synthetic-internal",
        "contains_pii": False,
        "curation_status": "approved",
        "ingestion_policy": "internal",
        "enabled": True,
    }
    document.update(overrides)
    return document


if __name__ == "__main__":
    unittest.main()
