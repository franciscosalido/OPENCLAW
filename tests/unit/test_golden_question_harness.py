from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from backend.agent0.golden_questions import (
    Citation,
    GOLDEN_FORBIDDEN_KEYS,
    GoldenQuestion,
    assert_golden_report_sanitized,
    run_golden_questions,
)
from scripts import run_golden_questions as golden_script


class EmptyRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        return ()


class WrongDocRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        return (
            Citation(
                question_id=question.question_id,
                source_id="wrong-source",
                doc_id="wrong_doc",
                chunk_id="wrong_doc:0",
                corpus=question.expected_corpus,
                collection_name=question.expected_collection,
                origin_path="docs/wrong.md",
                score=0.1,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class TrackingRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        self.calls.append((question.question_id, collection))
        return (
            Citation(
                question_id=question.question_id,
                source_id="source",
                doc_id=question.expected_doc_ids[0],
                chunk_id=f"{question.expected_doc_ids[0]}:0",
                corpus=question.expected_corpus,
                collection_name=question.expected_collection,
                origin_path="docs/source.md",
                score=1.0,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class GoldenQuestionHarnessTests(unittest.TestCase):
    def test_dry_run_uses_fake_retriever_and_passes_all_questions(self) -> None:
        result = run_golden_questions()

        self.assertEqual(result.report["mode"], "dry_run")
        self.assertEqual(result.report["total_questions"], 6)
        self.assertEqual(result.report["passed"], 6)
        self.assertEqual(result.report["failed"], 0)

    def test_custom_retriever_receives_mapped_collections(self) -> None:
        retriever = TrackingRetriever()

        run_golden_questions(retriever=retriever)

        self.assertEqual(len(retriever.calls), 6)
        self.assertIn(("iq-001", "openclaw_internal"), retriever.calls)
        self.assertIn(("fq-001", "openclaw_financial"), retriever.calls)

    def test_dry_run_does_not_generate_answer(self) -> None:
        result = run_golden_questions()

        self.assertNotIn("answer", result.report)
        self.assertTrue(_forbidden_keys_absent(result.report, {"answer", "prompt"}))

    def test_dry_run_report_sanitized(self) -> None:
        result = run_golden_questions()

        assert_golden_report_sanitized(result.report)

    def test_report_has_no_forbidden_keys(self) -> None:
        result = run_golden_questions()

        self.assertTrue(_forbidden_keys_absent(result.report, GOLDEN_FORBIDDEN_KEYS))

    def test_citation_present_true_when_expected_doc_recovered(self) -> None:
        result = run_golden_questions(retriever=TrackingRetriever())

        self.assertTrue(
            all(
                question["citation_present"]
                for question in _per_question(result.report)
            )
        )

    def test_citation_present_false_when_expected_doc_absent(self) -> None:
        result = run_golden_questions(retriever=WrongDocRetriever())

        self.assertEqual(result.report["passed"], 0)
        self.assertEqual(result.report["failed"], 6)
        self.assertTrue(
            all(
                not question["citation_present"]
                for question in _per_question(result.report)
            )
        )

    def test_coverage_and_citation_hit_rate_computed_correctly(self) -> None:
        passing = run_golden_questions(retriever=TrackingRetriever())
        failing = run_golden_questions(retriever=EmptyRetriever())

        self.assertEqual(passing.report["coverage"], 1.0)
        self.assertEqual(passing.report["citation_hit_rate"], 1.0)
        self.assertEqual(failing.report["coverage"], 1.0)
        self.assertEqual(failing.report["citation_hit_rate"], 0.0)

    def test_p50_and_p95_query_latency_computed(self) -> None:
        result = run_golden_questions()

        self.assertIsInstance(result.report["p50_query_ms"], float)
        self.assertIsInstance(result.report["p95_query_ms"], float)
        self.assertGreaterEqual(result.report["p50_query_ms"], 0.0)
        self.assertGreaterEqual(result.report["p95_query_ms"], 0.0)

    def test_cli_dry_run_writes_sanitized_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "golden.json"
            exit_code = golden_script.main(
                ["--dry-run", "--report-out", str(report_path)]
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["total_questions"], 6)
        assert_golden_report_sanitized(report)

    def test_smoke_requires_guard_env(self) -> None:
        self.assertEqual(golden_script.main(["--smoke"]), 2)


def _per_question(report: dict[str, object]) -> Sequence[dict[str, object]]:
    value = report["per_question"]
    if not isinstance(value, list):
        raise TypeError("per_question must be a list")
    return value


def _forbidden_keys_absent(value: object, forbidden: set[str] | frozenset[str]) -> bool:
    if isinstance(value, dict):
        return all(
            key not in forbidden and _forbidden_keys_absent(nested, forbidden)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return all(_forbidden_keys_absent(item, forbidden) for item in value)
    return True


if __name__ == "__main__":
    unittest.main()
