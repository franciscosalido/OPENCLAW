from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields

from backend.agent0.golden_questions import Citation


class CitationContractTests(unittest.TestCase):
    def test_citation_dataclass_is_frozen(self) -> None:
        citation = _citation()

        with self.assertRaises(FrozenInstanceError):
            citation.doc_id = "other"  # type: ignore[misc]

    def test_citation_has_all_required_fields(self) -> None:
        field_names = {field.name for field in fields(Citation)}

        self.assertEqual(
            field_names,
            {
                "question_id",
                "source_id",
                "doc_id",
                "chunk_id",
                "corpus",
                "collection_name",
                "origin_path",
                "score",
                "rank",
                "retrieval_mode",
                "chunk_index",
            },
        )

    def test_citation_has_no_content_fields(self) -> None:
        field_names = {field.name for field in fields(Citation)}

        self.assertTrue(
            {
                "answer",
                "text",
                "raw_text",
                "chunk_text",
                "vector",
                "embedding",
                "payload",
                "prompt",
            }.isdisjoint(field_names)
        )


def _citation() -> Citation:
    return Citation(
        question_id="iq-001",
        source_id="internal-current-state-001",
        doc_id="internal_current_state",
        chunk_id="internal_current_state:0",
        corpus="internal",
        collection_name="openclaw_internal",
        origin_path="docs/current_state.md",
        score=1.0,
        rank=1,
        retrieval_mode="fake",
    )


if __name__ == "__main__":
    unittest.main()
