from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.ingestion.fingerprint import (
    duplicate_hashes,
    file_sha256,
    normalized_text_sha256,
)
from backend.ingestion.pipeline import IngestionOptions, run_ingestion


def _write_manifest(root: Path, expected_hash: str) -> Path:
    manifest = root / "manifest.yaml"
    manifest.write_text(
        f"""
version: 1
documents:
  - source_id: synth-test-001
    doc_id: doc_a
    origin_path: docs/a.md
    source_type: md
    domain: macroeconomia
    language: pt-BR
    license: synthetic-internal
    contains_pii: false
    curation_status: approved
    ingestion_policy: financial
    enabled: true
    expected_hash: "{expected_hash}"
""",
        encoding="utf-8",
    )
    return manifest


class IngestionFingerprintTests(unittest.TestCase):
    def test_raw_file_sha256_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "doc.md"
            path.write_text("conteudo sintetico\n", encoding="utf-8")

            first = file_sha256(path)
            second = file_sha256(path)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_normalized_text_sha256_stable(self) -> None:
        first = normalized_text_sha256("texto   sintetico\ncontrolado")
        second = normalized_text_sha256("texto sintetico controlado")

        self.assertEqual(first, second)

    def test_dedup_by_hash_not_path(self) -> None:
        duplicates = duplicate_hashes(
            {
                "doc_a": "a" * 64,
                "doc_b": "a" * 64,
                "doc_c": "b" * 64,
            },
        )

        self.assertEqual(duplicates, {"doc_b"})

    def test_different_bytes_not_deduped(self) -> None:
        duplicates = duplicate_hashes({"doc_a": "a" * 64, "doc_b": "b" * 64})

        self.assertEqual(duplicates, set())

    def test_expected_hash_mismatch_rejects_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            docs.mkdir()
            (docs / "a.md").write_text("conteudo sintetico", encoding="utf-8")
            manifest = _write_manifest(root, "0" * 64)

            result = run_ingestion(IngestionOptions(manifest_path=manifest))

        per_document = result.report["per_document"]
        self.assertIsInstance(per_document, list)
        self.assertEqual(per_document[0]["status"], "rejected")
        self.assertEqual(per_document[0]["rejection_reason"], "expected_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
