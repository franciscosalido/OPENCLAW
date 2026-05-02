from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_golden_harness


FORBIDDEN_REPORT_KEYS = {
    "answer",
    "question",
    "prompt",
    "chunks",
    "chunk",
    "vectors",
    "vector",
    "payload",
    "qdrant_payload",
    "api_key",
    "authorization",
    "secret",
    "password",
    "headers",
    "raw_response",
    "raw_exception",
    "exception_message",
}
FORBIDDEN_REAL_TERMS = {
    "petr4",
    "vale3",
    "itub4",
    "bova11",
    "tesouro selic",
    "magalu",
    "petrobras",
    "vale",
    "itau",
    "bradesco",
}
REQUIRED_DOMAINS = {"macro", "allocation", "risk", "fixed_income", "funds"}


class GoldenHarnessTests(unittest.IsolatedAsyncioTestCase):
    def test_questions_yaml_loads_and_has_unique_ids(self) -> None:
        questions = run_golden_harness.load_questions()

        self.assertGreaterEqual(len(questions), 5)
        self.assertLessEqual(len(questions), 10)
        ids = [question.question_id for question in questions]
        self.assertEqual(len(ids), len(set(ids)))
        for question in questions:
            self.assertTrue(question.rationale)

    def test_questions_are_synthetic_and_cover_domains_and_modes(self) -> None:
        questions = run_golden_harness.load_questions()
        combined_text = " ".join(
            f"{question.question} {question.rationale}".lower()
            for question in questions
        )
        domains = {question.domain for question in questions}
        modes = {question.mode for question in questions}

        self.assertTrue(REQUIRED_DOMAINS.issubset(domains))
        self.assertTrue({"chat", "rag", "json"}.issubset(modes))
        for forbidden in FORBIDDEN_REAL_TERMS:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined_text)

    def test_golden_result_serialization_excludes_sensitive_content(self) -> None:
        result = run_golden_harness.GoldenResult(
            question_id="gq_test",
            domain="risk",
            mode="chat",
            route="local",
            alias="local_chat",
            used_rag=False,
            latency_ms=0.0,
            decision_id="decision",
            estimated_remote_tokens_avoided=10,
            answer_length_chars=30,
            error_category=None,
            fallback_applied=None,
            fallback_reason=None,
            quality_score=None,
        )
        data = result.to_json_dict()

        self.assertTrue(FORBIDDEN_REPORT_KEYS.isdisjoint({key.lower() for key in data}))
        self.assertEqual(data["answer_length_chars"], 30)

    def test_golden_result_cannot_be_skipped_and_failed(self) -> None:
        with self.assertRaises(ValueError):
            run_golden_harness.GoldenResult(
                question_id="gq_test",
                domain="risk",
                mode="chat",
                route="local",
                alias=None,
                used_rag=False,
                latency_ms=0.0,
                decision_id="decision",
                estimated_remote_tokens_avoided=0,
                answer_length_chars=0,
                error_category="chat_unavailable",
                fallback_applied=None,
                fallback_reason=None,
                quality_score=None,
                skipped=True,
                skipped_reason="offline",
            )

    async def test_dry_run_harness_produces_jsonl_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path, summary_path = await run_golden_harness.run_harness(
                output_dir=temp_dir,
                dry_run=True,
            )

            self.assertTrue(jsonl_path.exists())
            self.assertTrue(summary_path.exists())
            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            questions = run_golden_harness.load_questions()

            self.assertEqual(len(lines), len(questions))
            for line in lines:
                row = json.loads(line)
                self.assertTrue(
                    FORBIDDEN_REPORT_KEYS.isdisjoint({key.lower() for key in row})
                )
                self.assertEqual(row["latency_ms"], 0.0)
                self.assertIn(row["alias"], {"local_chat", "local_rag", "local_json"})
                self.assertIsNone(row["quality_score"])

            self.assertEqual(summary["total_questions"], len(questions))
            self.assertEqual(summary["failed"], 0)
            self.assertEqual(summary["skipped"], 0)
            self.assertIn("mean_latency_ms_by_alias", summary)
            self.assertIn("p95_latency_ms_by_alias", summary)
            self.assertFalse(summary["quality_score_present"])

    async def test_guard_env_prevents_accidental_runs(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdout.write") as write_mock,
        ):
            exit_code = await run_golden_harness.main_async(["--dry-run"])

        self.assertEqual(exit_code, 2)
        self.assertIn("opt-in", write_mock.call_args.args[0])

    async def test_guard_env_allows_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(os.environ, {"RUN_GOLDEN_HARNESS": "1"}, clear=True),
                patch("sys.stdout.write"),
            ):
                exit_code = await run_golden_harness.main_async(
                    ["--dry-run", "--output-dir", temp_dir]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(list(Path(temp_dir).glob("golden_results_*.jsonl")))
            self.assertTrue(list(Path(temp_dir).glob("golden_summary_*.json")))

    def test_reports_directory_is_gitignored(self) -> None:
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        self.assertIn("tests/golden/reports/", gitignore)


if __name__ == "__main__":
    unittest.main()
