from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, cast

import httpx

from scripts import run_rag_latency_baseline as baseline


def _result(
    *,
    run_type: str = "cold_start",
    alias: str = "local_rag",
    model: str = "qwen3:14b",
    total_ms: float = 1000.0,
    load_ms: float | None = None,
    eval_count: int | None = None,
    eval_duration_ms: float | None = None,
    keep_alive_applied: bool | None = None,
) -> baseline.BaselineRunResult:
    model_load_observed = baseline._model_load_observed(load_ms)
    typed_run_type = baseline._validate_run_type(run_type)
    return baseline.BaselineRunResult(
        run_type=typed_run_type,
        alias=alias,
        model=model,
        question_hash_8="abcdef12",
        question_length_chars=42,
        segment_ms={
            "embedding_ms": 1.0,
            "retrieval_ms": 2.0,
            "context_pack_ms": 3.0,
            "prompt_build_ms": 4.0,
            "generation_ms": 900.0,
            "total_ms": total_ms,
        },
        ollama_metrics_available=load_ms is not None,
        ollama_metrics_unavailable_reason=None
        if load_ms is not None
        else "not_forwarded_by_gateway",
        ollama_total_duration_ms=None,
        ollama_load_duration_ms=load_ms,
        ollama_eval_count=eval_count,
        ollama_eval_duration_ms=eval_duration_ms,
        ollama_prompt_eval_count=None,
        ollama_prompt_eval_duration_ms=None,
        model_load_observed=model_load_observed,
        run_type_verified=baseline._run_type_verified(
            run_type=typed_run_type,
            model_load_observed=model_load_observed,
            error_category=None,
        ),
        model_was_resident_before_run=False,
        resident_check_unavailable_reason=None,
        tokens_per_second=baseline._tokens_per_second(
            eval_count=eval_count,
            eval_duration_ms=eval_duration_ms,
        ),
        model_residency_enabled=keep_alive_applied,
        keep_alive_value="5m" if keep_alive_applied else None,
        keep_alive_applied=keep_alive_applied,
        keep_alive_ineffective=baseline._keep_alive_ineffective(
            run_type=typed_run_type,
            keep_alive_applied=keep_alive_applied,
            model_load_observed=model_load_observed,
        ),
        wall_ms=total_ms,
        ok=True,
        error_category=None,
    )


class RagLatencyBaselineTests(unittest.TestCase):
    def _records(self, report: dict[str, object]) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], report["records"])

    def _grouped_summary(
        self,
        report: dict[str, object],
    ) -> dict[str, dict[str, dict[str, object]]]:
        return cast(
            dict[str, dict[str, dict[str, object]]],
            report["summary_by_alias_and_run_type"],
        )

    def test_run_type_required_in_baseline_record(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])

        record = self._records(report)[0]

        self.assertEqual(record["run_type"], "cold_start")
        self.assertNotIn("run_context", record)

    def test_invalid_run_type_rejected_in_report_validation(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])
        bad_record = dict(self._records(report)[0])
        bad_record["run_type"] = "mixed"
        report["records"] = [bad_record]

        with self.assertRaisesRegex(ValueError, "valid run_type"):
            baseline.validate_report(report)

    def test_summary_grouped_by_alias_and_run_type(self) -> None:
        report = baseline.build_report(
            [
                _result(run_type="cold_start", total_ms=1000.0),
                _result(run_type="warm_model", total_ms=700.0),
            ]
        )

        summary = self._grouped_summary(report)

        self.assertIn("local_rag", summary)
        self.assertEqual(summary["local_rag"]["cold_start"]["mean_total_ms"], 1000.0)
        self.assertEqual(summary["local_rag"]["warm_model"]["mean_total_ms"], 700.0)

    def test_report_has_no_top_level_mixed_mean_total_ms(self) -> None:
        report = baseline.build_report(
            [
                _result(run_type="cold_start", total_ms=1000.0),
                _result(run_type="warm_model", total_ms=700.0),
            ]
        )

        self.assertNotIn("mean_total_ms", report)
        bad_report = dict(report)
        bad_report["mean_total_ms"] = 850.0
        with self.assertRaisesRegex(ValueError, "mixed top-level mean_total_ms"):
            baseline.validate_report(bad_report)

    def test_model_load_observed_derives_from_load_duration(self) -> None:
        self.assertIsNone(baseline._model_load_observed(None))
        self.assertFalse(baseline._model_load_observed(500.0))
        self.assertTrue(baseline._model_load_observed(501.0))

    def test_run_type_verified_derives_from_load_and_degraded_status(self) -> None:
        self.assertTrue(
            baseline._run_type_verified(
                run_type="cold_start",
                model_load_observed=True,
                error_category=None,
            )
        )
        self.assertTrue(
            baseline._run_type_verified(
                run_type="warm_model",
                model_load_observed=False,
                error_category=None,
            )
        )
        self.assertTrue(
            baseline._run_type_verified(
                run_type="degraded_qdrant",
                model_load_observed=None,
                error_category="RuntimeError",
            )
        )
        self.assertIsNone(
            baseline._run_type_verified(
                run_type="warm_model",
                model_load_observed=None,
                error_category=None,
            )
        )
        # Mislabelled cold start — model was already warm
        self.assertFalse(
            baseline._run_type_verified(
                run_type="cold_start",
                model_load_observed=False,
                error_category=None,
            )
        )
        # Cold start unverifiable — no Ollama metrics
        self.assertIsNone(
            baseline._run_type_verified(
                run_type="cold_start",
                model_load_observed=None,
                error_category=None,
            )
        )
        # Mislabelled warm — model loaded during claimed warm run
        self.assertFalse(
            baseline._run_type_verified(
                run_type="warm_model",
                model_load_observed=True,
                error_category=None,
            )
        )
        # Degraded run that did not actually fail
        self.assertFalse(
            baseline._run_type_verified(
                run_type="degraded_qdrant",
                model_load_observed=None,
                error_category=None,
            )
        )

    def test_tokens_per_second_computed_safely(self) -> None:
        self.assertEqual(
            baseline._tokens_per_second(eval_count=100, eval_duration_ms=2000.0),
            50.0,
        )
        self.assertIsNone(
            baseline._tokens_per_second(eval_count=100, eval_duration_ms=0.0)
        )
        self.assertIsNone(
            baseline._tokens_per_second(eval_count=None, eval_duration_ms=100.0)
        )

    def test_keep_alive_ineffective_flags_warm_reload_only(self) -> None:
        self.assertTrue(
            baseline._keep_alive_ineffective(
                run_type="warm_model",
                keep_alive_applied=True,
                model_load_observed=True,
            )
        )
        self.assertFalse(
            baseline._keep_alive_ineffective(
                run_type="warm_model",
                keep_alive_applied=True,
                model_load_observed=False,
            )
        )
        self.assertIsNone(
            baseline._keep_alive_ineffective(
                run_type="cold_start",
                keep_alive_applied=True,
                model_load_observed=True,
            )
        )
        self.assertIsNone(
            baseline._keep_alive_ineffective(
                run_type="warm_model",
                keep_alive_applied=False,
                model_load_observed=True,
            )
        )

    def test_report_records_keep_alive_fields(self) -> None:
        report = baseline.build_report(
            [
                _result(
                    run_type="warm_model",
                    load_ms=1000.0,
                    keep_alive_applied=True,
                )
            ]
        )

        record = self._records(report)[0]

        self.assertEqual(record["model_residency_enabled"], True)
        self.assertEqual(record["keep_alive_value"], "5m")
        self.assertEqual(record["keep_alive_applied"], True)
        self.assertEqual(record["keep_alive_ineffective"], True)

    def test_missing_metrics_get_safe_reason(self) -> None:
        self.assertEqual(
            baseline._ollama_metrics_unavailable_reason(
                run_type="warm_model",
                trace_present=True,
                metrics_available=False,
            ),
            "not_forwarded_by_gateway",
        )
        self.assertEqual(
            baseline._ollama_metrics_unavailable_reason(
                run_type="cold_start",
                trace_present=False,
                metrics_available=False,
            ),
            "not_present_in_response",
        )
        self.assertEqual(
            baseline._ollama_metrics_unavailable_reason(
                run_type="degraded_qdrant",
                trace_present=False,
                metrics_available=False,
            ),
            "not_applicable_degraded",
        )

    def test_ollama_ps_parser_handles_present_absent_and_invalid(self) -> None:
        payload = {"models": [{"name": "qwen3:14b"}]}

        self.assertTrue(
            baseline._parse_ollama_ps_residency(payload, model="qwen3:14b")
        )
        self.assertFalse(
            baseline._parse_ollama_ps_residency(payload, model="other:latest")
        )
        self.assertIsNone(
            baseline._parse_ollama_ps_residency({"models": "bad"}, model="qwen3:14b")
        )

    def test_residency_check_rejects_remote_url_without_calling_client(self) -> None:
        result = self.run_async(
            baseline.check_ollama_model_residency(
                model="qwen3:14b",
                base_url="https://example.com",
            )
        )

        self.assertIsNone(result.model_was_resident_before_run)
        self.assertEqual(result.resident_check_unavailable_reason, "non_local_url")

    def test_residency_check_handles_timeout(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout")

        async def run_check() -> baseline.ModelResidencyCheck:
            async with httpx.AsyncClient(
                base_url="http://127.0.0.1:11434",
                transport=httpx.MockTransport(handler),
            ) as client:
                return await baseline.check_ollama_model_residency(
                    model="qwen3:14b",
                    base_url="http://127.0.0.1:11434",
                    client=client,
                )

        result = self.run_async(run_check())

        self.assertIsNone(result.model_was_resident_before_run)
        self.assertEqual(result.resident_check_unavailable_reason, "timeout")

    def test_hardware_snapshot_has_no_username_path_or_hostname_keys(self) -> None:
        snapshot = baseline._hardware_snapshot()

        self.assertNotIn("username", snapshot)
        self.assertNotIn("hostname", snapshot)
        self.assertNotIn("path", snapshot)
        self.assertIn("platform_system", snapshot)
        self.assertIn("platform_machine", snapshot)
        self.assertIn("python_version", snapshot)

    def test_verify_only_accepts_valid_report(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])

        baseline.validate_report(report)

    def test_verify_only_rejects_legacy_report_missing_run_type(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])
        legacy_record = dict(self._records(report)[0])
        legacy_record.pop("run_type")
        report["records"] = [legacy_record]

        with self.assertRaisesRegex(ValueError, "valid run_type"):
            baseline.validate_report(report)

    def test_verify_report_file_reads_json(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])
        path = self.tmp_path() / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")

        baseline.verify_report_file(path)

    def test_sanitized_output_forbids_sensitive_keys(self) -> None:
        report = baseline.build_report([_result(run_type="cold_start")])
        bad_report = dict(report)
        bad_report["prompt"] = "FAKE_PROMPT_SHOULD_NOT_APPEAR"

        with self.assertRaisesRegex(ValueError, "Forbidden keys"):
            baseline.validate_report(bad_report)

    def tmp_path(self) -> Path:
        import tempfile

        return Path(tempfile.mkdtemp())

    def run_async(self, awaitable: Any) -> Any:
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
