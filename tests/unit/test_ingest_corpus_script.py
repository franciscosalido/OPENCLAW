from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from scripts import ingest_corpus


def _pending_manifest(root: Path) -> Path:
    manifest = root / "manifest.yaml"
    manifest.write_text(
        """
version: 1
documents:
  - source_id: synth-test-001
    doc_id: doc_pending
    origin_path: docs/pending.md
    source_type: md
    domain: macroeconomia
    language: pt-BR
    license: synthetic-internal
    contains_pii: false
    curation_status: pending
    ingestion_policy: financial
    enabled: true
""",
        encoding="utf-8",
    )
    return manifest


class IngestCorpusScriptTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            ingest_corpus.main(["--help"])

        self.assertEqual(ctx.exception.code, 0)

    def test_verify_only_writes_report_and_does_not_call_qdrant_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            with (
                patch("backend.rag.qdrant_store.QdrantVectorStore.ensure_collection") as ensure,
                patch("backend.rag.qdrant_store.QdrantVectorStore.upsert") as upsert,
                patch("backend.rag.qdrant_store.QdrantVectorStore.delete_document") as delete,
            ):
                exit_code = ingest_corpus.main(
                    [
                        "--manifest",
                        "data/corpus/manifest.yaml",
                        "--report-out",
                        str(report_path),
                    ],
                )

            data = cast(dict[str, Any], json.loads(report_path.read_text(encoding="utf-8")))

        self.assertEqual(exit_code, 0)
        self.assertEqual(data["mode"], "verify_only")
        ensure.assert_not_called()
        upsert.assert_not_called()
        delete.assert_not_called()

    def test_commit_requires_explicit_manifest(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            ingest_corpus.main(["--commit"])

        self.assertNotEqual(ctx.exception.code, 0)

    def test_commit_accepts_equals_form_manifest_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"

            exit_code = ingest_corpus.main(
                [
                    "--commit",
                    "--manifest=data/corpus/manifest.yaml",
                    "--report-out",
                    str(report_path),
                ],
            )
            data = cast(dict[str, Any], json.loads(report_path.read_text(encoding="utf-8")))

        self.assertEqual(exit_code, 0)
        self.assertEqual(data["mode"], "commit")

    def test_commit_blocked_on_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs").mkdir()
            (root / "docs" / "pending.md").write_text("conteudo sintetico", encoding="utf-8")
            manifest = _pending_manifest(root)

            with self.assertRaises(ValueError):
                ingest_corpus.main(["--manifest", str(manifest), "--commit"])

    def test_report_contains_no_forbidden_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            ingest_corpus.main(
                [
                    "--manifest",
                    "data/corpus/manifest.yaml",
                    "--report-out",
                    str(report_path),
                ],
            )
            data = cast(dict[str, Any], json.loads(report_path.read_text(encoding="utf-8")))

        forbidden = {
            "text",
            "raw_text",
            "normalized_text",
            "chunk",
            "chunks",
            "chunk_text",
            "vector",
            "vectors",
            "embedding",
            "embeddings",
            "payload",
            "prompt",
            "answer",
            "api_key",
            "authorization",
            "headers",
            "secret",
            "raw_exception",
            "exception_message",
            "traceback",
            "local_absolute_path",
            "username",
        }
        self.assertTrue(forbidden.isdisjoint(data))


if __name__ == "__main__":
    unittest.main()
