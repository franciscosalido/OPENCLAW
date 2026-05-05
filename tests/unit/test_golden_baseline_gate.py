from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import compare_golden_runs


BASELINE_DIR = Path("tests/golden/baseline")
BASELINE_SUMMARY = BASELINE_DIR / "gateway2_baseline_summary.json"
BASELINE_RESULTS = BASELINE_DIR / "gateway2_baseline_results.jsonl"
THRESHOLDS = BASELINE_DIR / "gateway2_regression_thresholds.yaml"


class GoldenBaselineGateTests(unittest.TestCase):
    def test_official_baseline_schema_is_valid(self) -> None:
        report = compare_golden_runs.verify_gateway2_summary(BASELINE_SUMMARY)

        self.assertEqual(report.summary["sprint"], "Gateway-2")
        self.assertEqual(len(report.results), report.summary["total_results"])

    def test_missing_question_fixture_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary, results = _baseline_copy()
            summary.pop("question_fixture_hash")
            path = _write_report(Path(tmpdir), summary, results)

            with self.assertRaises(compare_golden_runs.Gateway2GateError) as ctx:
                compare_golden_runs.verify_gateway2_summary(path)

        self.assertEqual(ctx.exception.exit_code, compare_golden_runs.EXIT_SCHEMA_SANITIZATION)

    def test_fixture_hash_mismatch_fails_with_exit_code_5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            candidate_summary["question_fixture_hash"] = "different_fixture_hash"
            for result in candidate_results:
                result["question_fixture_hash"] = "different_fixture_hash"
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            _output, exit_code = _compare_paths(baseline_path, candidate_path)

        self.assertEqual(exit_code, compare_golden_runs.EXIT_FIXTURE_CONFIG_MISMATCH)

    def test_missing_run_type_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary, results = _baseline_copy()
            results[0].pop("run_type")
            path = _write_report(Path(tmpdir), summary, results)

            with self.assertRaises(compare_golden_runs.Gateway2GateError) as ctx:
                compare_golden_runs.verify_gateway2_summary(path)

        self.assertEqual(ctx.exception.exit_code, compare_golden_runs.EXIT_SCHEMA_SANITIZATION)

    def test_mixed_cold_warm_aggregate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary, results = _baseline_copy()
            summary["mean_total_ms"] = 123.0
            path = _write_report(Path(tmpdir), summary, results)

            with self.assertRaises(compare_golden_runs.Gateway2GateError) as ctx:
                compare_golden_runs.verify_gateway2_summary(path)

        self.assertEqual(ctx.exception.exit_code, compare_golden_runs.EXIT_SCHEMA_SANITIZATION)

    def test_sanitization_prohibited_answer_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary, results = _baseline_copy()
            results[0]["answer"] = "must not be serialized"
            path = _write_report(Path(tmpdir), summary, results)

            with self.assertRaises(compare_golden_runs.Gateway2GateError) as ctx:
                compare_golden_runs.verify_gateway2_summary(path)

        self.assertEqual(ctx.exception.exit_code, compare_golden_runs.EXIT_SCHEMA_SANITIZATION)

    def test_citation_regression_fails_with_exit_code_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            for result in candidate_results:
                if result["alias"] == "local_rag" and result["run_type"] == "warm_model":
                    result["citation_present"] = False
                    break
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            _output, exit_code = _compare_paths(baseline_path, candidate_path)

        self.assertEqual(exit_code, compare_golden_runs.EXIT_CITATION_QUALITY)

    def test_latency_regression_fails_with_exit_code_4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            for result in candidate_results:
                if result["alias"] == "local_rag" and result["run_type"] == "warm_model":
                    result["total_ms"] = _as_float(result["total_ms"]) * 1.5
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            _output, exit_code = _compare_paths(baseline_path, candidate_path)

        self.assertEqual(exit_code, compare_golden_runs.EXIT_LATENCY_REGRESSION)

    def test_valid_candidate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            for result in candidate_results:
                if result["alias"] == "local_rag" and result["run_type"] == "warm_model":
                    result["total_ms"] = _as_float(result["total_ms"]) * 0.95
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            output, exit_code = _compare_paths(baseline_path, candidate_path)

        self.assertEqual(exit_code, compare_golden_runs.EXIT_OK)
        self.assertIn("status=pass", output)

    def test_gateway2_comparison_without_thresholds_fails_with_targeted_message(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            with patch("sys.stderr.write") as stderr_write:
                exit_code = compare_golden_runs.main(
                    [
                        "--baseline",
                        str(baseline_path),
                        "--candidate",
                        str(candidate_path),
                    ],
                )

        self.assertEqual(exit_code, compare_golden_runs.EXIT_FIXTURE_CONFIG_MISMATCH)
        written = "".join(str(call.args[0]) for call in stderr_write.call_args_list)
        self.assertIn(
            "--thresholds is required for Gateway-2 baseline comparison",
            written,
        )

    def test_missing_optional_ollama_metrics_pass_when_reason_present(self) -> None:
        report = compare_golden_runs.verify_gateway2_summary(BASELINE_SUMMARY)
        rag_rows = [row for row in report.results if row["alias"] == "local_rag"]

        self.assertTrue(rag_rows)
        self.assertTrue(
            all(row.get("metric_unavailable_reason") for row in rag_rows)
        )

    def test_thresholds_loaded_from_yaml(self) -> None:
        thresholds = compare_golden_runs.load_thresholds(THRESHOLDS)

        self.assertEqual(
            thresholds["thresholds_version"],
            "gateway2_regression_thresholds_v1",
        )
        self.assertIn("local_rag", thresholds["aliases"])

    def test_comparator_performs_no_network_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            baseline_summary, results = _baseline_copy()
            candidate_summary, candidate_results = _baseline_copy()
            baseline_path = _write_report(temp_path / "baseline", baseline_summary, results)
            candidate_path = _write_report(
                temp_path / "candidate",
                candidate_summary,
                candidate_results,
            )

            with patch("socket.socket", side_effect=AssertionError("network call")):
                _output, exit_code = _compare_paths(baseline_path, candidate_path)

        self.assertEqual(exit_code, compare_golden_runs.EXIT_OK)

    def test_generated_reports_ignored_and_official_baseline_not_ignored(self) -> None:
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        self.assertIn("reports/golden/", gitignore)
        self.assertIn("reports/gateway2/", gitignore)
        self.assertIn("reports/ci/", gitignore)
        self.assertIn("!tests/golden/baseline/gateway2_baseline_summary.json", gitignore)
        self.assertIn("!tests/golden/baseline/gateway2_baseline_results.jsonl", gitignore)
        self.assertIn(
            "!tests/golden/baseline/gateway2_regression_thresholds.yaml",
            gitignore,
        )


def _baseline_copy() -> tuple[dict[str, object], list[dict[str, object]]]:
    summary = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
    results = [
        json.loads(line)
        for line in BASELINE_RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return summary, results


def _write_report(
    directory: Path,
    summary: dict[str, object],
    results: list[dict[str, object]],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    summary = dict(summary)
    summary["results_artifact"] = "results.jsonl"
    summary_path = directory / "summary.json"
    results_path = directory / "results.jsonl"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    results_path.write_text(
        "\n".join(json.dumps(result, sort_keys=True) for result in results) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _compare_paths(baseline_path: Path, candidate_path: Path) -> tuple[str, int]:
    try:
        return compare_golden_runs.compare_gateway2_reports(
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            thresholds_path=THRESHOLDS,
        )
    except compare_golden_runs.Gateway2GateError as exc:
        return str(exc), exc.exit_code


def _as_float(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise AssertionError("expected numeric value")
    return float(value)


if __name__ == "__main__":
    unittest.main()
