from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast
from unittest.mock import patch

import httpx

from backend.gateway.routing_policy import FallbackReason
from scripts import run_local_agent
from scripts import test_gateway1_proof_of_life as proof


PROBE_KEYS = {
    "service",
    "ok",
    "latency_ms",
    "error_category",
    "missing_aliases",
}
RUNNER_KEYS = {
    "name",
    "ok",
    "route",
    "alias",
    "used_rag",
    "latency_ms",
    "decision_id",
    "estimated_remote_tokens_avoided",
    "answer_length_chars",
    "error_category",
    "fallback_applied",
    "fallback_reason",
    "model_call_attempted",
}
SUMMARY_KEYS = {
    "run_id",
    "timestamp_utc",
    "gateway_sprint",
    "criteria_manifest_ref",
    "service_probes",
    "runner_tests",
    "passed",
    "failed",
    "skipped",
    "criteria_met",
    "overall_passed",
}


def _fake_result(
    *,
    alias: str = "local_chat",
    used_rag: bool = False,
    answer: str = "resposta sintetica",
    error_category: str | None = None,
    fallback_reason: FallbackReason | None = None,
) -> run_local_agent.AgentRunResult:
    return run_local_agent.AgentRunResult(
        answer=answer,
        route="local",
        alias=alias,
        used_rag=used_rag,
        latency_ms=12.3,
        decision_id="decision-123",
        estimated_remote_tokens_avoided=42,
        error_category=error_category,
        fallback_applied=fallback_reason is not None,
        fallback_from_alias="local_rag" if fallback_reason is not None else None,
        fallback_to_alias="local_chat" if fallback_reason is not None else None,
        fallback_reason=fallback_reason,
        fallback_chain=(fallback_reason,) if fallback_reason is not None else None,
    )


class GatewayProofOfLifeUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_local_url_guard_accepts_localhost_and_loopback(self) -> None:
        self.assertTrue(proof.is_local_url("http://127.0.0.1:4000/v1"))
        self.assertTrue(proof.is_local_url("http://localhost:6333"))

    def test_local_url_guard_rejects_remote_urls(self) -> None:
        self.assertFalse(proof.is_local_url("https://api.example.com/v1"))
        self.assertFalse(proof.is_local_url("http://192.168.1.1:4000/v1"))

    def test_probe_result_serialization_is_allowlisted(self) -> None:
        result = proof.ProbeResult(
            service="litellm",
            ok=False,
            latency_ms=1.2,
            error_category="alias_missing",
            missing_aliases=("local_chat",),
        )
        data = result.to_json_dict()

        self.assertTrue(set(data).issubset(PROBE_KEYS))
        proof.assert_sanitized(data)

    def test_summary_serialization_is_allowlisted(self) -> None:
        summary = proof.GatewayProofOfLifeSummary(
            run_id="run",
            timestamp_utc="2026-05-02T00:00:00Z",
            gateway_sprint="Gateway-1",
            criteria_manifest_ref=proof.CRITERIA_MANIFEST_REF,
            service_probes={
                "ollama": proof.ProbeResult("ollama", True, 1.0),
            },
            runner_tests={
                "dry_run": proof.RunnerSmokeResult(
                    name="dry_run",
                    ok=True,
                    route="local",
                    alias="local_chat",
                    used_rag=False,
                    latency_ms=0.0,
                    decision_id="decision",
                    estimated_remote_tokens_avoided=1,
                    answer_length_chars=20,
                ),
            },
            passed=("G1-01",),
            failed=(),
            skipped=(),
            criteria_met={"G1-01": True},
            overall_passed=True,
        )
        data = summary.to_json_dict()

        self.assertEqual(set(data), SUMMARY_KEYS)
        proof.assert_sanitized(data)

    def test_recursive_sanitizer_catches_prohibited_key(self) -> None:
        with self.assertRaises(ValueError):
            proof.assert_sanitized({"nested": {"api_key": "x"}})

    def test_recursive_sanitizer_catches_fake_sensitive_value(self) -> None:
        with self.assertRaises(ValueError):
            proof.assert_sanitized({"safe_key": "FAKE_PROMPT_SHOULD_NOT_APPEAR"})

    def test_recursive_sanitizer_catches_answer_key_in_smoke_output(self) -> None:
        # "answer" is legitimate in AgentRunResult but must not appear in smoke
        # summaries — PROHIBITED_SMOKE_SUMMARY_KEYS extends the base set with it.
        with self.assertRaises(ValueError):
            proof.assert_sanitized({"answer": "some answer text"})

    async def test_dry_run_criterion_success(self) -> None:
        result = await proof.run_dry_run_smoke()
        data = result.to_json_dict()

        self.assertTrue(result.ok)
        self.assertEqual(data["alias"], "local_chat")
        self.assertEqual(data["latency_ms"], 0.0)
        proof.assert_sanitized(data)

    async def test_local_chat_criterion_success_with_fake_runner(self) -> None:
        async def fake_run_agent(**kwargs: object) -> run_local_agent.AgentRunResult:
            self.assertFalse(kwargs.get("use_rag", False))
            return _fake_result(alias="local_chat", used_rag=False)

        with patch("scripts.test_gateway1_proof_of_life.run_local_agent.run_agent", fake_run_agent):
            result = await proof.run_local_chat_smoke()

        self.assertTrue(result.ok)
        self.assertEqual(result.alias, "local_chat")
        proof.assert_sanitized(result.to_json_dict())

    async def test_rag_success_outcome_is_accepted(self) -> None:
        async def fake_run_agent(**kwargs: object) -> run_local_agent.AgentRunResult:
            self.assertTrue(kwargs.get("use_rag"))
            return _fake_result(alias="local_rag", used_rag=True)

        with patch("scripts.test_gateway1_proof_of_life.run_local_agent.run_agent", fake_run_agent):
            result = await proof.run_rag_smoke()

        self.assertTrue(result.ok)
        self.assertEqual(result.alias, "local_rag")

    async def test_rag_fallback_outcome_is_accepted(self) -> None:
        async def fake_run_agent(**kwargs: object) -> run_local_agent.AgentRunResult:
            self.assertTrue(kwargs.get("use_rag"))
            return _fake_result(
                alias="local_chat",
                used_rag=False,
                fallback_reason=FallbackReason.QDRANT_UNAVAILABLE,
            )

        with patch("scripts.test_gateway1_proof_of_life.run_local_agent.run_agent", fake_run_agent):
            result = await proof.run_rag_smoke()

        self.assertTrue(result.ok)
        self.assertEqual(result.alias, "local_chat")
        self.assertEqual(result.fallback_reason, "qdrant_unavailable")

    async def test_forced_degradation_uses_fallback_metadata(self) -> None:
        result = await proof.run_forced_qdrant_degradation_smoke()
        data = result.to_json_dict()

        self.assertTrue(result.ok)
        self.assertEqual(data["alias"], "local_chat")
        self.assertEqual(data["used_rag"], False)
        self.assertIn(
            data["fallback_reason"],
            {"qdrant_unavailable", "rag_unavailable"},
        )
        proof.assert_sanitized(data)

    async def test_policy_block_verifies_no_model_call(self) -> None:
        result = await proof.run_policy_block_smoke()
        data = result.to_json_dict()

        self.assertTrue(result.ok)
        self.assertEqual(data["route"], "blocked")
        self.assertEqual(data["error_category"], "blocked")
        self.assertEqual(data["model_call_attempted"], False)
        proof.assert_sanitized(data)

    def test_overall_passed_logic_requires_mandatory_criteria(self) -> None:
        criteria = {criterion: True for criterion in proof.MANDATORY_CRITERIA}
        summary = proof._build_summary(
            run_id="run",
            probes={},
            runner_tests={},
            criteria_met=criteria,
            skipped=set(),
        )
        self.assertTrue(summary.overall_passed)

        criteria["G1-06"] = False
        summary = proof._build_summary(
            run_id="run",
            probes={},
            runner_tests={},
            criteria_met=criteria,
            skipped=set(),
        )
        self.assertFalse(summary.overall_passed)
        self.assertIn("G1-06", summary.failed)

    def test_summary_json_writes_to_tmp_path(self) -> None:
        criteria = {criterion: True for criterion in proof.MANDATORY_CRITERIA}
        summary = proof._build_summary(
            run_id="run",
            probes={},
            runner_tests={},
            criteria_met=criteria,
            skipped=set(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = proof.write_summary(temp_dir, summary)
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["run_id"], "run")
        self.assertTrue(loaded["overall_passed"])

    async def test_guard_env_prevents_accidental_runs(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdout.write") as write_mock,
        ):
            exit_code = await proof.main_async(["--output-dir", "/tmp/unused"])

        self.assertEqual(exit_code, 2)
        self.assertIn("opt-in", write_mock.call_args.args[0])

    async def test_main_writes_summary_when_guard_enabled_with_fakes(self) -> None:
        async def fake_local_chat() -> proof.RunnerSmokeResult:
            return proof.RunnerSmokeResult(
                name="local_chat",
                ok=True,
                route="local",
                alias="local_chat",
                used_rag=False,
                latency_ms=1.0,
                decision_id="decision",
                estimated_remote_tokens_avoided=1,
                answer_length_chars=20,
            )

        async def fake_rag() -> proof.RunnerSmokeResult:
            return proof.RunnerSmokeResult(
                name="rag",
                ok=True,
                route="local",
                alias="local_rag",
                used_rag=True,
                latency_ms=1.0,
                decision_id="decision",
                estimated_remote_tokens_avoided=1,
                answer_length_chars=20,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(
                    os.environ,
                    {"RUN_GATEWAY1_PROOF_OF_LIFE": "1"},
                    clear=True,
                ),
                patch.object(proof, "probe_ollama", _fake_probe("ollama", True)),
                patch.object(proof, "probe_qdrant", _fake_probe("qdrant", True)),
                patch.object(proof, "probe_litellm", _fake_litellm_probe(True)),
                patch.object(proof, "run_local_chat_smoke", fake_local_chat),
                patch.object(proof, "run_rag_smoke", fake_rag),
                patch("sys.stdout.write"),
            ):
                exit_code = await proof.main_async(["--output-dir", temp_dir])

            self.assertEqual(exit_code, 0)
            summaries = list(Path(temp_dir).glob("gateway1_proof_of_life_*.json"))
            self.assertEqual(len(summaries), 1)
            data = json.loads(summaries[0].read_text(encoding="utf-8"))

        self.assertTrue(data["overall_passed"])
        proof.assert_sanitized(cast(dict[str, object], data))

    async def test_async_probes_are_gathered_into_all_service_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(
                    os.environ,
                    {"RUN_GATEWAY1_PROOF_OF_LIFE": "1"},
                    clear=True,
                ),
                patch.object(proof, "probe_ollama", _fake_probe("ollama", True)),
                patch.object(proof, "probe_qdrant", _fake_probe("qdrant", True)),
                patch.object(proof, "probe_litellm", _fake_litellm_probe(True)),
                patch.object(proof, "run_local_chat_smoke", _fake_runner_smoke("local_chat", True)),
                patch.object(proof, "run_rag_smoke", _fake_runner_smoke("rag", True)),
            ):
                summary, _ = await proof.run_proof_of_life(output_dir=temp_dir)

        self.assertEqual(set(summary.service_probes), {"ollama", "qdrant", "litellm"})
        self.assertTrue(summary.service_probes["ollama"].ok)
        self.assertTrue(summary.service_probes["qdrant"].ok)
        self.assertTrue(summary.service_probes["litellm"].ok)

    async def test_async_probe_failure_is_converted_to_probe_result(self) -> None:
        class RaisingAsyncClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                del args, kwargs

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                del exc_type, exc, traceback

            async def get(self, url: str, **kwargs: object) -> object:
                del url, kwargs
                raise httpx.ConnectError("FAKE_SECRET_MESSAGE")

        with patch("scripts.test_gateway1_proof_of_life.httpx.AsyncClient", RaisingAsyncClient):
            result = await proof.probe_ollama("http://127.0.0.1:11434")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_category, "connection")
        data = result.to_json_dict()
        self.assertNotIn("FAKE_SECRET_MESSAGE", json.dumps(data))
        proof.assert_sanitized(data)

    async def test_failed_async_probe_does_not_hide_other_service_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(
                    os.environ,
                    {"RUN_GATEWAY1_PROOF_OF_LIFE": "1"},
                    clear=True,
                ),
                patch.object(proof, "probe_ollama", _fake_probe("ollama", True)),
                patch.object(proof, "probe_qdrant", _fake_probe("qdrant", False, "connection")),
                patch.object(proof, "probe_litellm", _fake_litellm_probe(True)),
            ):
                summary, _ = await proof.run_proof_of_life(output_dir=temp_dir)

        self.assertEqual(set(summary.service_probes), {"ollama", "qdrant", "litellm"})
        self.assertTrue(summary.service_probes["ollama"].ok)
        self.assertFalse(summary.service_probes["qdrant"].ok)
        self.assertEqual(summary.service_probes["qdrant"].error_category, "connection")
        self.assertTrue(summary.service_probes["litellm"].ok)

    async def test_litellm_async_probe_does_not_leak_authorization(self) -> None:
        sentinel = "FAKE_API_KEY_SHOULD_NOT_APPEAR"

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"data": [{"id": alias} for alias in proof.REQUIRED_ALIASES]}

        class CapturingAsyncClient:
            captured_headers: Mapping[str, str] | None = None

            def __init__(self, *args: object, **kwargs: object) -> None:
                del args, kwargs

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                del exc_type, exc, traceback

            async def get(
                self,
                url: str,
                *,
                headers: Mapping[str, str] | None = None,
            ) -> Response:
                del url
                CapturingAsyncClient.captured_headers = headers
                return Response()

        with patch("scripts.test_gateway1_proof_of_life.httpx.AsyncClient", CapturingAsyncClient):
            result = await proof.probe_litellm(
                "http://127.0.0.1:4000/v1",
                api_key=sentinel,
            )

        self.assertTrue(result.ok)
        self.assertIn("Authorization", CapturingAsyncClient.captured_headers or {})
        serialized = json.dumps(result.to_json_dict())
        self.assertNotIn(sentinel, serialized)
        self.assertNotIn("Authorization", serialized)
        proof.assert_sanitized(result.to_json_dict())

    async def test_remote_url_guard_runs_before_async_probes(self) -> None:
        async def fail_probe(*args: object, **kwargs: object) -> proof.ProbeResult:
            del args, kwargs
            self.fail("probe should not run after remote URL guard failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(
                    os.environ,
                    {
                        "RUN_GATEWAY1_PROOF_OF_LIFE": "1",
                        "QUIMERA_LLM_BASE_URL": "https://api.example.com/v1",
                    },
                    clear=True,
                ),
                patch.object(proof, "probe_ollama", fail_probe),
                patch.object(proof, "probe_qdrant", fail_probe),
                patch.object(proof, "probe_litellm", fail_probe),
            ):
                summary, _ = await proof.run_proof_of_life(output_dir=temp_dir)

        self.assertFalse(summary.criteria_met["G1-02"])
        self.assertEqual(set(summary.service_probes), {"ollama", "qdrant", "litellm"})
        for service_probe in summary.service_probes.values():
            self.assertFalse(service_probe.ok)
            self.assertEqual(service_probe.error_category, "local_url_rejected")


class GatewayProofOfLifeProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_litellm_probe_reports_missing_aliases(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"data": [{"id": "local_chat"}]}

        class AliasAsyncClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                del args, kwargs

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                del exc_type, exc, traceback

            async def get(
                self,
                url: str,
                *,
                headers: Mapping[str, str] | None = None,
            ) -> Response:
                del url, headers
                return Response()

        with patch("scripts.test_gateway1_proof_of_life.httpx.AsyncClient", AliasAsyncClient):
            result = await proof.probe_litellm(
                "http://127.0.0.1:4000/v1",
                api_key="dev-key",
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_category, "alias_missing")
        self.assertIn("local_rag", result.missing_aliases)


def _fake_probe(
    service: str,
    ok: bool,
    error_category: str | None = None,
) -> Any:
    async def fake(base_url: str) -> proof.ProbeResult:
        del base_url
        return proof.ProbeResult(
            service=service,
            ok=ok,
            latency_ms=1.0,
            error_category=error_category,
        )

    return fake


def _fake_litellm_probe(ok: bool) -> Any:
    async def fake(base_url: str, *, api_key: str | None) -> proof.ProbeResult:
        del base_url, api_key
        return proof.ProbeResult(service="litellm", ok=ok, latency_ms=1.0)

    return fake


def _fake_runner_smoke(name: str, ok: bool) -> Any:
    async def fake() -> proof.RunnerSmokeResult:
        return proof.RunnerSmokeResult(
            name=name,
            ok=ok,
            route="local",
            alias="local_chat" if name == "local_chat" else "local_rag",
            used_rag=name == "rag",
            latency_ms=1.0,
            decision_id="decision",
            estimated_remote_tokens_avoided=1,
            answer_length_chars=20,
        )

    return fake


if __name__ == "__main__":
    unittest.main()
