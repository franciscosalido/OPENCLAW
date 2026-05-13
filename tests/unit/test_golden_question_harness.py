from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

from backend.agent0.golden_questions import (
    Citation,
    CollectionName,
    GOLDEN_FORBIDDEN_KEYS,
    GoldenQuestion,
    assert_golden_report_sanitized,
    run_golden_questions,
)
from backend.ingestion.bootstrap import CorpusName
from scripts import run_golden_questions as golden_script


REQUIRED_REPORT_FIELDS = frozenset(
    {
        "run_id",
        "timestamp_utc",
        "mode",
        "total_questions",
        "enabled_questions",
        "skipped_questions",
        "evaluated_questions",
        "passed",
        "failed",
        "coverage",
        "citation_hit_rate",
        "p50_query_ms",
        "p95_query_ms",
        "per_question",
    }
)
REQUIRED_PER_QUESTION_FIELDS = frozenset(
    {
        "question_id",
        "expected_corpus",
        "expected_collection",
        "expected_doc_ids",
        "citation_present",
        "matched_doc_ids",
        "latency_ms",
        "status",
        "failure_reason",
    }
)


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


class CrossCollectionRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        wrong_collection: CollectionName = (
            "openclaw_internal"
            if question.expected_collection == "openclaw_financial"
            else "openclaw_financial"
        )
        wrong_corpus: CorpusName = (
            "internal" if question.expected_corpus == "financial" else "financial"
        )
        return (
            Citation(
                question_id=question.question_id,
                source_id="source",
                doc_id=question.expected_doc_ids[0],
                chunk_id=f"{question.expected_doc_ids[0]}:0",
                corpus=wrong_corpus,
                collection_name=wrong_collection,
                origin_path="docs/source.md",
                score=0.9,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class WrongCorpusRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        wrong_corpus: CorpusName = (
            "internal" if question.expected_corpus == "financial" else "financial"
        )
        return (
            Citation(
                question_id=question.question_id,
                source_id="source",
                doc_id=question.expected_doc_ids[0],
                chunk_id=f"{question.expected_doc_ids[0]}:0",
                corpus=wrong_corpus,
                collection_name=question.expected_collection,
                origin_path="docs/source.md",
                score=0.9,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class PartialHitRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        return (
            Citation(
                question_id=question.question_id,
                source_id="source",
                doc_id=question.expected_doc_ids[0],
                chunk_id=f"{question.expected_doc_ids[0]}:0",
                corpus=question.expected_corpus,
                collection_name=question.expected_collection,
                origin_path="docs/source.md",
                score=0.8,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class ZeroScoreRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        return (
            Citation(
                question_id=question.question_id,
                source_id="source",
                doc_id=question.expected_doc_ids[0],
                chunk_id=f"{question.expected_doc_ids[0]}:0",
                corpus=question.expected_corpus,
                collection_name=question.expected_collection,
                origin_path="docs/source.md",
                score=0.0,
                rank=1,
                retrieval_mode="fake",
            ),
        )


class DuplicateCitationRetriever:
    def retrieve(
        self,
        question: GoldenQuestion,
        *,
        collection: str,
    ) -> tuple[Citation, ...]:
        citation = Citation(
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
        )
        return (citation, citation)


class GoldenQuestionHarnessTests(unittest.TestCase):
    TOTAL_GOLDEN_QUESTIONS = 14
    INTERNAL_GOLDEN_QUESTIONS = 5
    FINANCIAL_GOLDEN_QUESTIONS = 9

    def test_dry_run_uses_fake_retriever_and_passes_all_questions(self) -> None:
        result = run_golden_questions()

        self.assertEqual(result.report["mode"], "dry_run")
        self.assertEqual(result.report["total_questions"], self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(result.report["passed"], self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(result.report["failed"], 0)

    def test_custom_retriever_receives_mapped_collections(self) -> None:
        retriever = TrackingRetriever()

        run_golden_questions(retriever=retriever)

        self.assertEqual(len(retriever.calls), self.TOTAL_GOLDEN_QUESTIONS)
        self.assertIn(("iq-001", "openclaw_internal"), retriever.calls)
        self.assertIn(("iq-005", "openclaw_internal"), retriever.calls)
        self.assertIn(("fq-001", "openclaw_financial"), retriever.calls)
        self.assertIn(("fq-009", "openclaw_financial"), retriever.calls)

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

    def test_report_contains_all_required_top_level_fields(self) -> None:
        result = run_golden_questions()

        self.assertTrue(
            REQUIRED_REPORT_FIELDS.issubset(result.report),
            f"missing fields: {REQUIRED_REPORT_FIELDS - set(result.report)}",
        )

    def test_per_question_rows_have_exact_required_fields(self) -> None:
        result = run_golden_questions()

        for row in _per_question(result.report):
            self.assertEqual(
                set(row),
                REQUIRED_PER_QUESTION_FIELDS,
                f"field drift in {row.get('question_id')}: "
                f"extras={set(row) - REQUIRED_PER_QUESTION_FIELDS}, "
                f"missing={REQUIRED_PER_QUESTION_FIELDS - set(row)}",
            )

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
        self.assertEqual(result.report["failed"], self.TOTAL_GOLDEN_QUESTIONS)
        self.assertTrue(
            all(
                not question["citation_present"]
                for question in _per_question(result.report)
            )
        )

    def test_correct_doc_from_wrong_collection_does_not_pass(self) -> None:
        result = run_golden_questions(retriever=CrossCollectionRetriever())

        self.assertEqual(result.report["passed"], 0)
        self.assertEqual(result.report["failed"], result.report["evaluated_questions"])
        self.assertTrue(
            all(
                not question["citation_present"]
                for question in _per_question(result.report)
            )
        )

    def test_correct_doc_from_wrong_corpus_does_not_pass(self) -> None:
        result = run_golden_questions(retriever=WrongCorpusRetriever())

        self.assertEqual(result.report["passed"], 0)
        self.assertEqual(result.report["failed"], result.report["evaluated_questions"])

    def test_partial_doc_id_hit_is_sufficient_for_citation_present(self) -> None:
        result = run_golden_questions(retriever=PartialHitRetriever())

        self.assertEqual(result.report["passed"], result.report["evaluated_questions"])
        self.assertTrue(
            all(
                question["citation_present"]
                for question in _per_question(result.report)
            )
        )

    def test_zero_score_citation_is_valid_and_passes(self) -> None:
        result = run_golden_questions(retriever=ZeroScoreRetriever())

        self.assertEqual(result.report["passed"], result.report["evaluated_questions"])

    def test_citation_rejects_negative_score(self) -> None:
        with self.assertRaises(ValueError):
            Citation(
                question_id="iq-001",
                source_id="source",
                doc_id="internal_current_state",
                chunk_id="internal_current_state:0",
                corpus="internal",
                collection_name="openclaw_internal",
                origin_path="docs/source.md",
                score=-0.001,
                rank=1,
                retrieval_mode="fake",
            )

    def test_citation_rejects_zero_rank(self) -> None:
        with self.assertRaises(ValueError):
            Citation(
                question_id="iq-001",
                source_id="source",
                doc_id="internal_current_state",
                chunk_id="internal_current_state:0",
                corpus="internal",
                collection_name="openclaw_internal",
                origin_path="docs/source.md",
                score=1.0,
                rank=0,
                retrieval_mode="fake",
            )

    def test_duplicate_citations_do_not_inflate_pass_count(self) -> None:
        result = run_golden_questions(retriever=DuplicateCitationRetriever())

        self.assertLessEqual(
            result.report["passed"],
            result.report["evaluated_questions"],
        )
        for row in _per_question(result.report):
            matched_doc_ids = row["matched_doc_ids"]
            if not isinstance(matched_doc_ids, list):
                raise TypeError("matched_doc_ids must be a list")
            self.assertEqual(len(matched_doc_ids), len(set(matched_doc_ids)))

    def test_coverage_and_citation_hit_rate_computed_correctly(self) -> None:
        passing = run_golden_questions(retriever=TrackingRetriever())
        failing = run_golden_questions(retriever=EmptyRetriever())

        self.assertEqual(passing.report["total_questions"], self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(
            passing.report["enabled_questions"],
            self.TOTAL_GOLDEN_QUESTIONS,
        )
        self.assertEqual(passing.report["skipped_questions"], 0)
        self.assertEqual(
            passing.report["evaluated_questions"],
            self.TOTAL_GOLDEN_QUESTIONS,
        )
        self.assertEqual(passing.report["coverage"], 1.0)
        self.assertEqual(passing.report["citation_hit_rate"], 1.0)
        self.assertEqual(failing.report["coverage"], 1.0)
        self.assertEqual(failing.report["citation_hit_rate"], 0.0)

    def test_coverage_tracks_enabled_questions_not_pass_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            internal_path = Path(tmpdir) / "internal_questions.yaml"
            financial_path = Path(tmpdir) / "financial_questions.yaml"
            internal_path.write_text(
                """
questions:
  - question_id: iq-001
    text: qual o estado atual do GW-07?
    expected_corpus: internal
    expected_collection: openclaw_internal
    expected_doc_ids:
      - internal_current_state
    domain: internal
    language: pt-BR
    enabled: true
  - question_id: iq-004
    text: pergunta interna desabilitada
    expected_corpus: internal
    expected_collection: openclaw_internal
    expected_doc_ids:
      - internal_current_state
    domain: internal
    language: pt-BR
    enabled: false
""".lstrip(),
                encoding="utf-8",
            )
            financial_path.write_text("questions: []\n", encoding="utf-8")

            result = run_golden_questions(
                retriever=TrackingRetriever(),
                internal_path=internal_path,
                financial_path=financial_path,
            )

        self.assertEqual(result.report["total_questions"], 2)
        self.assertEqual(result.report["enabled_questions"], 1)
        self.assertEqual(result.report["skipped_questions"], 1)
        self.assertEqual(result.report["evaluated_questions"], 1)
        self.assertEqual(result.report["coverage"], 0.5)
        self.assertEqual(result.report["citation_hit_rate"], 1.0)
        self.assertEqual(len(_per_question(result.report)), 1)

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
        self.assertEqual(report["total_questions"], self.TOTAL_GOLDEN_QUESTIONS)
        assert_golden_report_sanitized(report)

    def test_sanitizer_rejects_ingestion_forbidden_keys_too(self) -> None:
        with self.assertRaises(ValueError):
            assert_golden_report_sanitized({"secret": "redacted"})
        with self.assertRaises(ValueError):
            assert_golden_report_sanitized({"local_absolute_path": "/tmp/example"})

    def test_smoke_requires_guard_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(golden_script.main(["--smoke"]), 2)

    def test_smoke_blocked_even_with_partial_env(self) -> None:
        with patch.dict(os.environ, {"RUN_GOLDEN_SMOKE": "yes"}, clear=True):
            self.assertEqual(golden_script.main(["--smoke"]), 2)
        with patch.dict(os.environ, {"RUN_GOLDEN_SMOKE": "true"}, clear=True):
            self.assertEqual(golden_script.main(["--smoke"]), 2)

    def test_harness_per_question_results_are_deterministic(self) -> None:
        perf_counter_values = _deterministic_perf_counter_values(
            runs=2,
            questions_per_run=self.TOTAL_GOLDEN_QUESTIONS,
        )

        with patch(
            "backend.agent0.golden_questions.time.perf_counter",
            side_effect=perf_counter_values,
        ):
            result_a = run_golden_questions(retriever=TrackingRetriever())
            result_b = run_golden_questions(retriever=TrackingRetriever())

        self.assertEqual(
            result_a.report["per_question"],
            result_b.report["per_question"],
        )
        self.assertNotEqual(result_a.report["run_id"], result_b.report["run_id"])


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


def _deterministic_perf_counter_values(
    *,
    runs: int,
    questions_per_run: int,
) -> list[float]:
    values: list[float] = []
    for _ in range(runs):
        for index in range(questions_per_run):
            started_at = float(index)
            values.extend([started_at, started_at + 0.001])
    return values


if __name__ == "__main__":
    unittest.main()
