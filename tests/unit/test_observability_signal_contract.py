from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import patch

from backend.gateway.observability_contract import (
    AGENT_RUN_RESULT_KEYS,
    DECISION_LOG_KEYS,
    FALLBACK_EVENT_KEYS,
    GOLDEN_RESULT_KEYS,
    GOLDEN_SUMMARY_KEYS,
    PROHIBITED_SIGNAL_KEYS,
    RAG_RUN_TRACE_KEYS,
    ROUTER_DECISION_KEYS,
    SAFE_FALLBACK_REASON_VALUES,
    SAFE_ROUTER_REASON_VALUES,
    TOKEN_ECONOMY_RECORD_KEYS,
    assert_signal_allowlisted,
    token_economy_canonical_signal,
)
from backend.gateway.routing_policy import (
    FallbackReason,
    RemoteEscalationPolicy,
    RouteBlockReason,
    RoutingDecisionLogger,
    build_token_economy_record,
    decide_route,
)
from backend.rag.run_trace import build_rag_run_trace
from scripts import run_golden_harness, run_local_agent


SENSITIVE_SENTINEL = "PRIVATE_PROMPT_api_key_headers_model_weights_path"


class ObservabilitySignalContractTests(unittest.IsolatedAsyncioTestCase):
    def test_router_decision_signals_are_allowlisted_for_core_routes(self) -> None:
        cases = [
            decide_route(
                task_type="agent0_chat",
                estimated_prompt_tokens=10,
                estimated_completion_tokens=20,
                contains_sensitive_context=False,
                high_value_task=False,
                policy=RemoteEscalationPolicy(),
            ),
            decide_route(
                task_type="agent0_chat",
                estimated_prompt_tokens=10,
                estimated_completion_tokens=20,
                contains_sensitive_context=False,
                high_value_task=False,
                policy=RemoteEscalationPolicy(per_request_token_limit=1),
            ),
            decide_route(
                task_type="trade_execution",
                estimated_prompt_tokens=10,
                estimated_completion_tokens=20,
                contains_sensitive_context=False,
                high_value_task=False,
                policy=RemoteEscalationPolicy(),
            ),
            decide_route(
                task_type="agent0_chat",
                estimated_prompt_tokens=10,
                estimated_completion_tokens=20,
                contains_sensitive_context=False,
                high_value_task=True,
                policy=RemoteEscalationPolicy(
                    remote_enabled=True,
                    allowed_remote_providers=("review_stub",),
                ),
            ),
        ]

        for decision in cases:
            with self.subTest(route=decision.route.value, reason=decision.reason):
                data = decision.to_log_dict()
                assert_signal_allowlisted(
                    data,
                    allowlist=ROUTER_DECISION_KEYS,
                    signal_name="RouterDecision",
                )
                self.assertTrue(data["decision_id"])
                self.assertIn(data["reason"], SAFE_ROUTER_REASON_VALUES)
                self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(data))

    def test_token_economy_record_signal_is_allowlisted_and_canonicalized(self) -> None:
        decision = decide_route(
            task_type="agent0_chat",
            estimated_prompt_tokens=12,
            estimated_completion_tokens=34,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )
        record = build_token_economy_record(decision)
        raw = record.to_log_dict()
        canonical = token_economy_canonical_signal(raw)

        assert_signal_allowlisted(
            raw,
            allowlist=TOKEN_ECONOMY_RECORD_KEYS,
            signal_name="TokenEconomyRecord",
        )
        assert_signal_allowlisted(
            canonical,
            allowlist=TOKEN_ECONOMY_RECORD_KEYS,
            signal_name="TokenEconomyRecordCanonical",
        )
        self.assertEqual(canonical["decision_id"], decision.decision_id)
        self.assertIsInstance(canonical["estimated_remote_tokens_avoided"], int)
        self.assertGreaterEqual(
            cast(int, canonical["estimated_remote_tokens_avoided"]),
            0,
        )

    def test_rag_run_trace_signal_is_allowlisted(self) -> None:
        trace = build_rag_run_trace(
            collection_name="gw19_synthetic_collection",
            embedding_backend="gateway_litellm_current",
            embedding_model="nomic-embed-text",
            embedding_alias="quimera_embed",
            embedding_dimensions=768,
            expected_dimensions=768,
            retrieval_latency_ms=1.5,
            generation_latency_ms=12.5,
            chunk_count=3,
            gateway_alias="local_rag",
            guard_result={
                "sampled_count": 2,
                "metadata_absent_count": 0,
                "backend_matches": True,
                "payload": "must be ignored",
            },
            total_latency_ms=14.0,
        )
        data = trace.to_log_dict()

        assert_signal_allowlisted(
            data,
            allowlist=RAG_RUN_TRACE_KEYS,
            signal_name="RagRunTrace",
        )
        self.assertEqual(data["gateway_alias"], "local_rag")
        self.assertEqual(data["chunk_count"], 3)
        self.assertNotIn("payload", json.dumps(data))

    async def test_fallback_event_is_allowlisted_and_correlated_with_result(self) -> None:
        events: list[dict[str, object]] = []

        class BoundLogger:
            def __init__(self, event: dict[str, object]) -> None:
                self.event = event

            def info(self, message: str) -> None:
                self.event["message"] = message
                events.append(self.event)

        def fake_bind(**kwargs: object) -> BoundLogger:
            event = kwargs["event"]
            assert isinstance(event, dict)
            return BoundLogger(event)

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError(SENSITIVE_SENTINEL)

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            return "fallback answer"

        with patch("scripts.run_local_agent.logger.bind", fake_bind):
            result = await run_local_agent.run_agent(
                question=SENSITIVE_SENTINEL,
                use_rag=True,
                rag_call=rag_call,
                chat_call=chat_call,
            )
        output = result.to_json_dict()

        self.assertEqual(len(events), 1)
        event = events[0]
        assert_signal_allowlisted(
            event,
            allowlist=FALLBACK_EVENT_KEYS | {"message"},
            signal_name="FallbackEvent",
        )
        self.assertEqual(event["event"], "agent_fallback")
        self.assertEqual(event["fallback_reason"], FallbackReason.RAG_UNAVAILABLE.value)
        self.assertIn(event["fallback_reason"], SAFE_FALLBACK_REASON_VALUES)
        self.assertEqual(event["decision_id"], output["decision_id"])
        self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(event))
        assert_signal_allowlisted(
            output,
            allowlist=AGENT_RUN_RESULT_KEYS,
            signal_name="AgentRunResult",
        )

    async def test_non_fallback_run_emits_no_fallback_event(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            return "answer"

        with patch("scripts.run_local_agent.logger.bind") as bind_mock:
            result = await run_local_agent.run_agent(
                question=SENSITIVE_SENTINEL,
                chat_call=chat_call,
            )

        bind_mock.assert_not_called()
        data = result.to_json_dict()
        assert_signal_allowlisted(
            data,
            allowlist=AGENT_RUN_RESULT_KEYS,
            signal_name="AgentRunResult",
        )
        self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(data))

    def test_decision_log_jsonl_is_allowlisted(self) -> None:
        decision = decide_route(
            task_type="agent0_chat",
            estimated_prompt_tokens=10,
            estimated_completion_tokens=20,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RoutingDecisionLogger(Path(temp_dir) / "decisions", rotate_daily=False)
            path = logger.append(decision)
            assert path is not None
            rows = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(rows), 1)
        row = json.loads(rows[0])
        assert_signal_allowlisted(
            row,
            allowlist=DECISION_LOG_KEYS,
            signal_name="DecisionLog",
        )
        self.assertIn(row["reason"], SAFE_ROUTER_REASON_VALUES)
        self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(row))

    async def test_dry_run_output_signal_has_required_token_economy(self) -> None:
        result = await run_local_agent.run_agent(
            question=SENSITIVE_SENTINEL,
            dry_run=True,
        )
        data = result.to_json_dict()

        assert_signal_allowlisted(
            data,
            allowlist=AGENT_RUN_RESULT_KEYS,
            signal_name="AgentRunResult",
        )
        self.assertIsInstance(data["estimated_remote_tokens_avoided"], int | float)
        self.assertGreaterEqual(cast(int, data["estimated_remote_tokens_avoided"]), 0)
        self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(data))

    async def test_estimated_remote_tokens_avoided_exists_across_runner_paths(self) -> None:
        async def chat_ok(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            return "answer"

        async def chat_fail(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise RuntimeError(SENSITIVE_SENTINEL)

        async def rag_fail(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError(SENSITIVE_SENTINEL)

        cases = [
            await run_local_agent.run_agent(question="ok", chat_call=chat_ok),
            await run_local_agent.run_agent(question="dry", dry_run=True),
            await run_local_agent.run_agent(
                question="blocked",
                policy_loader=lambda: RemoteEscalationPolicy(per_request_token_limit=1),
                chat_call=chat_fail,
            ),
            await run_local_agent.run_agent(
                question="fallback",
                use_rag=True,
                rag_call=rag_fail,
                chat_call=chat_ok,
            ),
            await run_local_agent.run_agent(
                question="fallback failure",
                use_rag=True,
                rag_call=rag_fail,
                chat_call=chat_fail,
            ),
        ]

        for result in cases:
            with self.subTest(result=result):
                data = result.to_json_dict()
                self.assertIn("estimated_remote_tokens_avoided", data)
                self.assertIsInstance(
                    data["estimated_remote_tokens_avoided"],
                    int | float,
                )
                self.assertGreaterEqual(
                    cast(int, data["estimated_remote_tokens_avoided"]),
                    0,
                )
                self.assertNotIn(SENSITIVE_SENTINEL, json.dumps(data))

    async def test_golden_harness_dry_run_reports_are_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path, summary_path = await run_golden_harness.run_harness(
                output_dir=temp_dir,
                dry_run=True,
            )
            rows = [
                json.loads(line)
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            ]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertGreater(len(rows), 0)
        for row in rows:
            assert_signal_allowlisted(
                row,
                allowlist=GOLDEN_RESULT_KEYS,
                signal_name="GoldenResult",
            )
            self.assertIsNone(row["quality_score"])
            self.assertNotIn("answer", row)
        assert_signal_allowlisted(
            summary,
            allowlist=GOLDEN_SUMMARY_KEYS,
            signal_name="GoldenSummary",
        )
        self.assertFalse(summary["quality_score_present"])

    def test_prohibited_key_contract_is_canonical(self) -> None:
        expected = {
            "prompt",
            "chunks",
            "vectors",
            "api_key",
            "headers",
            "raw_user_input",
            "model_weights_path",
        }

        self.assertTrue(expected.issubset(PROHIBITED_SIGNAL_KEYS))


if __name__ == "__main__":
    unittest.main()
