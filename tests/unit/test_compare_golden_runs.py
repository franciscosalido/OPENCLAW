from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import compare_golden_runs


def _summary(
    *,
    passed: int = 8,
    total_questions: int = 8,
    local_chat_latency: float = 100.0,
    local_rag_latency: float = 200.0,
    tokens_avoided: float = 1000.0,
    fallback_count: int = 0,
) -> dict[str, object]:
    return {
        "run_id": "run",
        "timestamp_utc": "2026-05-02T00:00:00Z",
        "total_questions": total_questions,
        "passed": passed,
        "failed": total_questions - passed,
        "skipped": 0,
        "fallback_count": fallback_count,
        "mean_latency_ms_by_alias": {
            "local_chat": local_chat_latency,
            "local_rag": local_rag_latency,
        },
        "p95_latency_ms_by_alias": {
            "local_chat": local_chat_latency,
            "local_rag": local_rag_latency,
        },
        "total_estimated_remote_tokens_avoided": tokens_avoided,
        "quality_score_present": False,
        "model_under_test_aliases": ["local_chat", "local_rag"],
    }


class CompareGoldenRunsTests(unittest.TestCase):
    def test_compare_passes_when_candidate_is_within_threshold(self) -> None:
        output, exit_code = compare_golden_runs.compare_summaries(
            _summary(),
            _summary(local_chat_latency=110.0, local_rag_latency=210.0),
            latency_threshold_pct=20.0,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("golden_run_comparison", output)
        self.assertIn("pass_rate_delta=0.0000", output)

    def test_compare_detects_pass_rate_regression(self) -> None:
        output, exit_code = compare_golden_runs.compare_summaries(
            _summary(passed=8),
            _summary(passed=7),
            latency_threshold_pct=20.0,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("pass_rate_delta=-0.1250", output)

    def test_compare_detects_latency_regression_over_threshold(self) -> None:
        output, exit_code = compare_golden_runs.compare_summaries(
            _summary(local_chat_latency=100.0),
            _summary(local_chat_latency=130.0),
            latency_threshold_pct=20.0,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("local_chat | 100.0 | 130.0 | 30.0", output)

    def test_main_reads_summary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline = Path(temp_dir) / "baseline.json"
            candidate = Path(temp_dir) / "candidate.json"
            baseline.write_text(json.dumps(_summary()), encoding="utf-8")
            candidate.write_text(json.dumps(_summary()), encoding="utf-8")

            exit_code = compare_golden_runs.main(
                [
                    "--baseline",
                    str(baseline),
                    "--candidate",
                    str(candidate),
                    "--latency-threshold-pct",
                    "20",
                ]
            )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
