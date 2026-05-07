from __future__ import annotations

import unittest

from backend.ingestion.manifest import CorpusDocument
from backend.ingestion.sanitizer import reject_manifest_pii, sanitize_parsed_text


def _document(*, contains_pii: bool = False) -> CorpusDocument:
    return CorpusDocument.model_validate(
        {
            "source_id": "synth-test-001",
            "doc_id": "doc_teste",
            "origin_path": "docs/doc_teste.md",
            "source_type": "md",
            "domain": "internal",
            "language": "pt-BR",
            "license": "synthetic-internal",
            "contains_pii": contains_pii,
            "curation_status": "approved",
            "ingestion_policy": "internal",
            "enabled": True,
        },
    )


class IngestionSanitizerTests(unittest.TestCase):
    def test_manifest_pii_rejected_before_parsing(self) -> None:
        result = reject_manifest_pii(_document(contains_pii=True))

        self.assertEqual(result.status, "contains_pii_manifest")
        self.assertIsNone(result.pii_pattern_category)

    def test_accepts_safe_text(self) -> None:
        result = sanitize_parsed_text("Texto sintetico seguro para curadoria local.")

        self.assertTrue(result.accepted)

    def test_detects_cpf_with_punctuation(self) -> None:
        result = sanitize_parsed_text("Identificador ficticio 123.456.789-00.")

        self.assertEqual(result.status, "pii_detected")
        self.assertEqual(result.pii_pattern_category, "cpf_punctuated")

    def test_detects_cpf_without_punctuation(self) -> None:
        result = sanitize_parsed_text("Identificador ficticio 12345678900.")

        self.assertEqual(result.status, "pii_detected")
        self.assertEqual(result.pii_pattern_category, "cpf_unformatted")

    def test_detects_email(self) -> None:
        result = sanitize_parsed_text("Contato sintetico pessoa@example.com.")

        self.assertEqual(result.status, "pii_detected")
        self.assertEqual(result.pii_pattern_category, "email")

    def test_detects_brazilian_phone(self) -> None:
        result = sanitize_parsed_text("Contato sintetico (11) 91234-5678.")

        self.assertEqual(result.status, "pii_detected")
        self.assertEqual(result.pii_pattern_category, "br_phone")


if __name__ == "__main__":
    unittest.main()
