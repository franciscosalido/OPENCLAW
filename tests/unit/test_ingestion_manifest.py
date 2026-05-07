from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.ingestion.manifest import CorpusManifest, load_manifest, resolve_corpus_path


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "source_id": "synth-test-001",
        "doc_id": "doc_teste",
        "origin_path": "docs/doc_teste.md",
        "source_type": "md",
        "domain": "macroeconomia",
        "language": "pt-BR",
        "license": "synthetic-internal",
        "contains_pii": False,
        "curation_status": "approved",
        "ingestion_policy": "financial",
        "enabled": True,
    }
    document.update(overrides)
    return document


def _manifest_yaml(document: dict[str, object]) -> str:
    lines = ["version: 1", "documents:"]
    for index, (key, value) in enumerate(document.items()):
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        prefix = "  -" if index == 0 else "   "
        lines.append(f"{prefix} {key}: {rendered}")
    return "\n".join(lines) + "\n"


class IngestionManifestTests(unittest.TestCase):
    def test_manifest_schema_valid(self) -> None:
        manifest = CorpusManifest.model_validate({"documents": [_document()]})

        self.assertEqual(len(manifest.documents), 1)
        self.assertEqual(manifest.documents[0].language, "pt-BR")

    def test_invalid_source_type_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CorpusManifest.model_validate({"documents": [_document(source_type="html")]})

    def test_path_traversal_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CorpusManifest.model_validate(
                {"documents": [_document(origin_path="../private.md")]},
            )

    def test_duplicate_doc_id_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CorpusManifest.model_validate(
                {
                    "documents": [
                        _document(source_id="synth-test-001"),
                        _document(source_id="synth-test-002"),
                    ],
                },
            )

    def test_duplicate_source_id_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CorpusManifest.model_validate(
                {
                    "documents": [
                        _document(doc_id="doc_teste_a", origin_path="docs/doc_teste_a.md"),
                        _document(doc_id="doc_teste_b", origin_path="docs/doc_teste_b.md"),
                    ],
                },
            )

    def test_load_manifest_uses_safe_yaml_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.yaml"
            manifest_path.write_text(_manifest_yaml(_document()), encoding="utf-8")

            manifest = load_manifest(manifest_path)

        self.assertEqual(manifest.documents[0].doc_id, "doc_teste")

    def test_resolve_path_stays_under_corpus_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.yaml"
            document = CorpusManifest.model_validate({"documents": [_document()]}).documents[0]

            resolved = resolve_corpus_path(manifest_path, document)

        self.assertEqual(resolved.name, "doc_teste.md")


if __name__ == "__main__":
    unittest.main()
