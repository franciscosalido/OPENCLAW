from __future__ import annotations

import unittest

from backend.agent0.e2e_report import (
    assert_e2e_report_sanitized,
    build_e2e_report,
)
from backend.agent0.golden_questions import Citation
from backend.agent0.openclaw import Answer


class Agent0E2EReportTests(unittest.TestCase):
    def test_e2e_report_sanitized(self) -> None:
        report = build_e2e_report(
            [
                ("iq-001", _answer(citation_present=True)),
                ("fq-001", _answer(citation_present=False)),
            ]
        )

        assert_e2e_report_sanitized(report)
        self.assertEqual(report["total_questions"], 2)
        self.assertEqual(report["failed_question_ids"], ["fq-001"])
        self.assertEqual(report["citation_hit_rate"], 0.5)
        self.assertNotIn("answer", report)
        self.assertNotIn("question", report)

    def test_e2e_report_rejects_forbidden_fields(self) -> None:
        with self.assertRaises(ValueError):
            assert_e2e_report_sanitized({"answer": "redacted"})


def _answer(*, citation_present: bool) -> Answer:
    return Answer(
        answer="Resposta omitida do relatório.",
        citations=(
            (
                Citation(
                    question_id="iq-001",
                    source_id="source",
                    doc_id="internal_current_state",
                    chunk_id="internal_current_state#0",
                    corpus="internal",
                    collection_name="openclaw_internal",
                    origin_path="docs/current_state.md",
                    score=1.0,
                    rank=1,
                    retrieval_mode="fake",
                    chunk_index=0,
                )
            ),
        )
        if citation_present
        else (),
        route="local_rag",
        corpus="internal",
        latency_ms=10.0,
        citation_present=citation_present,
        fallback_reason=None,
        error_category=None,
    )


if __name__ == "__main__":
    unittest.main()
