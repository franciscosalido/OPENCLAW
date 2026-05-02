from __future__ import annotations

import json
import inspect
import unittest
from collections.abc import Mapping
from typing import Any
from typing import cast
from unittest.mock import patch

from backend.gateway.routing_policy import (
    FallbackReason,
    RemoteEscalationPolicy,
    RouteDecisionKind,
    RouteBlockReason,
    TaskRiskLevel,
    TokenBudgetClass,
    RouterDecision,
    decide_route,
    load_routing_policy,
)
from scripts import run_local_agent


REQUIRED_KEYS = {
    "answer",
    "route",
    "alias",
    "used_rag",
    "latency_ms",
    "decision_id",
    "estimated_remote_tokens_avoided",
}
OPTIONAL_KEYS = {
    "error_category",
    "fallback_applied",
    "fallback_from_alias",
    "fallback_to_alias",
    "fallback_reason",
    "fallback_chain",
    "block_reason",
}
FORBIDDEN_OUTPUT_KEYS = {
    "query",
    "question",
    "prompt",
    "system_prompt",
    "user_prompt",
    "answer_raw",
    "raw_response",
    "raw_exception",
    "exception_message",
    "chunks",
    "chunk",
    "chunk_text",
    "retrieved_context",
    "context_text",
    "vectors",
    "vector",
    "embeddings",
    "embedding",
    "payload",
    "qdrant_payload",
    "documents",
    "portfolio",
    "carteira",
    "api_key",
    "authorization",
    "secret",
    "password",
    "headers",
    "traceback",
}
BLOCKED_ANSWER = "Request blocked by local routing policy."
DRY_RUN_ANSWER = "Dry run: no model call executed."
FAILURE_ANSWER = "Local Agent-0 execution failed."


def _assert_safe_schema(
    test_case: unittest.TestCase,
    data: Mapping[str, object],
    *,
    expect_error: str | None = None,
) -> None:
    test_case.assertTrue(REQUIRED_KEYS.issubset(data))
    extra_keys = set(data) - REQUIRED_KEYS - OPTIONAL_KEYS
    test_case.assertEqual(extra_keys, set())
    if expect_error is None:
        test_case.assertNotIn("error_category", data)
    else:
        test_case.assertEqual(data["error_category"], expect_error)
    test_case.assertIsInstance(data["latency_ms"], int | float)
    test_case.assertGreaterEqual(cast(float, data["latency_ms"]), 0.0)
    test_case.assertIsInstance(data["estimated_remote_tokens_avoided"], int | float)
    test_case.assertGreaterEqual(
        cast(int, data["estimated_remote_tokens_avoided"]),
        0,
    )
    test_case.assertIsInstance(data["decision_id"], str)
    test_case.assertTrue(data["decision_id"])
    test_case.assertTrue(FORBIDDEN_OUTPUT_KEYS.isdisjoint({key.lower() for key in data}))


def _assert_fallback_metadata(
    test_case: unittest.TestCase,
    data: Mapping[str, object],
    *,
    reason: FallbackReason,
) -> None:
    test_case.assertEqual(data["fallback_applied"], True)
    test_case.assertEqual(data["fallback_from_alias"], "local_rag")
    test_case.assertEqual(data["fallback_to_alias"], "local_chat")
    test_case.assertEqual(data["fallback_reason"], reason.value)
    test_case.assertEqual(data["fallback_chain"], [reason.value])


class RunLocalAgentCliTests(unittest.TestCase):
    def test_missing_question_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            run_local_agent.parse_args([])

        self.assertNotEqual(ctx.exception.code, 0)

    def test_rag_and_json_together_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            run_local_agent.parse_args(["pergunta", "--rag", "--json"])

        self.assertNotEqual(ctx.exception.code, 0)

    def test_help_exits_zero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            run_local_agent.parse_args(["--help"])

        self.assertEqual(ctx.exception.code, 0)

    def test_parse_args_rejects_invalid_boundaries(self) -> None:
        invalid_cases = [
            ["pergunta", "--max-tokens", "0"],
            ["pergunta", "--max-tokens", "-1"],
            ["pergunta", "--temperature", "-0.1"],
            ["pergunta", "--temperature", "2.1"],
            ["pergunta", "--output", "yaml"],
        ]

        for args in invalid_cases:
            with self.subTest(args=args):
                with self.assertRaises(SystemExit):
                    run_local_agent.parse_args(args)

    def test_parse_args_accepts_temperature_bounds(self) -> None:
        self.assertEqual(
            run_local_agent.parse_args(["pergunta", "--temperature", "0.0"]).temperature,
            0.0,
        )
        self.assertEqual(
            run_local_agent.parse_args(["pergunta", "--temperature", "2.0"]).temperature,
            2.0,
        )


class RunLocalAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_alias_contract_matrix(self) -> None:
        cases = [
            {"kwargs": {}, "alias": "local_chat", "used_rag": False},
            {"kwargs": {"use_json": True}, "alias": "local_json", "used_rag": False},
            {"kwargs": {"use_rag": True}, "alias": "local_rag", "used_rag": True},
        ]

        for case in cases:
            with self.subTest(case=case):
                seen: dict[str, object] = {}

                async def chat_call(
                    question: str,
                    *,
                    alias: str,
                    max_tokens: int | None,
                    temperature: float | None,
                    response_format: Mapping[str, object] | None,
                ) -> str:
                    del question, max_tokens, temperature, response_format
                    seen["alias"] = alias
                    return "answer"

                async def rag_call(
                    question: str,
                    *,
                    max_tokens: int | None,
                    temperature: float | None,
                ) -> str:
                    del question, max_tokens, temperature
                    seen["alias"] = "local_rag"
                    return "rag answer"

                kwargs = case["kwargs"]
                assert isinstance(kwargs, dict)
                result = await run_local_agent.run_agent(
                    question="pergunta",
                    chat_call=chat_call,
                    rag_call=rag_call,
                    **kwargs,
                )

                self.assertEqual(result.alias, case["alias"])
                self.assertEqual(result.used_rag, case["used_rag"])
                self.assertEqual(seen["alias"], case["alias"])
                _assert_safe_schema(self, result.to_json_dict())

    async def test_default_mode_selects_local_chat(self) -> None:
        seen: dict[str, object] = {}

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            self.assertEqual(question, "pergunta")
            seen.update(
                {
                    "alias": alias,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "response_format": response_format,
                }
            )
            return "answer"

        result = await run_local_agent.run_agent(
            question="pergunta",
            max_tokens=123,
            temperature=0.1,
            chat_call=chat_call,
        )

        self.assertEqual(result.answer, "answer")
        self.assertEqual(result.alias, "local_chat")
        self.assertFalse(result.used_rag)
        self.assertEqual(seen["alias"], "local_chat")
        self.assertEqual(seen["max_tokens"], 123)
        self.assertEqual(seen["temperature"], 0.1)
        self.assertIsNone(seen["response_format"])

    async def test_json_mode_selects_local_json(self) -> None:
        seen: dict[str, object] = {}

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del max_tokens, temperature
            self.assertEqual(question, "pergunta")
            seen["alias"] = alias
            seen["response_format"] = response_format
            return '{"ok": true}'

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_json=True,
            chat_call=chat_call,
        )

        self.assertEqual(result.alias, "local_json")
        self.assertFalse(result.used_rag)
        self.assertEqual(seen["alias"], "local_json")
        self.assertEqual(seen["response_format"], {"type": "json_object"})

    async def test_rag_mode_selects_rag_path(self) -> None:
        called = {"rag": False}

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            self.assertIsNone(max_tokens)
            self.assertIsNone(temperature)
            self.assertEqual(question, "pergunta")
            called["rag"] = True
            return "rag answer"

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_rag=True,
            rag_call=rag_call,
        )

        self.assertTrue(called["rag"])
        self.assertEqual(result.alias, "local_rag")
        self.assertTrue(result.used_rag)
        self.assertEqual(result.answer, "rag answer")

    async def test_dry_run_does_not_call_model(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise AssertionError("chat should not be called")

        result = await run_local_agent.run_agent(
            question="pergunta",
            dry_run=True,
            chat_call=chat_call,
        )

        self.assertEqual(result.answer, DRY_RUN_ANSWER)
        self.assertEqual(result.alias, "local_chat")
        self.assertEqual(result.latency_ms, 0.0)
        _assert_safe_schema(self, result.to_json_dict())

    async def test_output_json_returns_safe_schema(self) -> None:
        result = await run_local_agent.run_agent(
            question="pergunta",
            dry_run=True,
        )

        rendered = run_local_agent.render_result(
            result,
            output="json",
            show_metadata=False,
        )
        data = json.loads(rendered)

        _assert_safe_schema(self, data)

    async def test_routing_decision_happens_before_execution(self) -> None:
        events: list[str] = []
        original_decide = decide_route

        def wrapped_decide(**kwargs: Any) -> RouterDecision:
            events.append("decision")
            return original_decide(**kwargs)

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            events.append("chat")
            return "answer"

        with patch("scripts.run_local_agent.decide_route", wrapped_decide):
            await run_local_agent.run_agent(question="pergunta", chat_call=chat_call)

        self.assertEqual(events, ["decision", "chat"])

    async def test_policy_blocked_decision_prevents_model_call(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise AssertionError("chat should not be called")

        result = await run_local_agent.run_agent(
            question="pergunta",
            chat_call=chat_call,
            policy_loader=lambda: RemoteEscalationPolicy(per_request_token_limit=1),
        )

        self.assertEqual(result.error_category, "blocked")
        self.assertEqual(result.route, "blocked")
        self.assertEqual(result.answer, BLOCKED_ANSWER)
        self.assertEqual(result.latency_ms, 0.0)
        self.assertFalse(result.fallback_applied)
        self.assertEqual(result.block_reason, FallbackReason.BUDGET_EXCEEDED.value)
        _assert_safe_schema(self, result.to_json_dict(), expect_error="blocked")

    async def test_chat_unavailable_produces_safe_error_category(self) -> None:
        attempts: list[str] = []

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            attempts.append(alias)
            del question, max_tokens, temperature, response_format
            raise RuntimeError("sensitive private message")

        result = await run_local_agent.run_agent(
            question="pergunta",
            chat_call=chat_call,
        )

        data = result.to_json_dict()
        self.assertEqual(result.answer, FAILURE_ANSWER)
        self.assertEqual(data["error_category"], "chat_unavailable")
        self.assertEqual(attempts, ["local_chat"])
        self.assertNotIn("sensitive private message", json.dumps(data))
        _assert_safe_schema(self, data, expect_error="chat_unavailable")

    async def test_json_unavailable_does_not_fallback_to_chat(self) -> None:
        attempts: list[str] = []

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, max_tokens, temperature, response_format
            attempts.append(alias)
            raise RuntimeError("json private failure")

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_json=True,
            chat_call=chat_call,
        )

        self.assertEqual(attempts, ["local_json"])
        self.assertEqual(result.alias, "local_json")
        _assert_safe_schema(
            self,
            result.to_json_dict(),
            expect_error="json_unavailable",
        )

    async def test_json_mode_keeps_model_answer_as_string_inside_runner_schema(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            return '{"foo": "bar"}'

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_json=True,
            chat_call=chat_call,
        )
        data = json.loads(
            run_local_agent.render_result(
                result,
                output="json",
                show_metadata=False,
            )
        )

        self.assertEqual(data["answer"], '{"foo": "bar"}')
        self.assertEqual(data["alias"], "local_json")
        _assert_safe_schema(self, data)

    async def test_rag_unavailable_falls_back_once_to_local_chat(self) -> None:
        calls: list[str] = []

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, max_tokens, temperature, response_format
            calls.append(alias)
            return "fallback chat answer"

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError("service down with private details")

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_rag=True,
            chat_call=chat_call,
            rag_call=rag_call,
        )

        data = result.to_json_dict()
        self.assertNotIn("error_category", data)
        self.assertEqual(data["answer"], "fallback chat answer")
        self.assertEqual(data["alias"], "local_chat")
        self.assertFalse(data["used_rag"])
        self.assertEqual(calls, ["local_chat"])
        self.assertNotIn("service down", json.dumps(data))
        _assert_safe_schema(self, data)
        _assert_fallback_metadata(
            self,
            data,
            reason=FallbackReason.RAG_UNAVAILABLE,
        )

    async def test_qdrant_unavailable_fallback_reason_is_typed(self) -> None:
        class QdrantUnavailableError(RuntimeError):
            pass

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            return "fallback chat answer"

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise QdrantUnavailableError("private details")

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_rag=True,
            chat_call=chat_call,
            rag_call=rag_call,
        )
        data = result.to_json_dict()

        _assert_fallback_metadata(
            self,
            data,
            reason=FallbackReason.QDRANT_UNAVAILABLE,
        )

    async def test_rag_unavailable_and_fallback_chat_failure_has_no_double_fallback(self) -> None:
        calls: list[str] = []

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, max_tokens, temperature, response_format
            calls.append(alias)
            raise RuntimeError("fallback private failure")

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError("rag private failure")

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_rag=True,
            chat_call=chat_call,
            rag_call=rag_call,
        )
        data = result.to_json_dict()

        self.assertEqual(calls, ["local_chat"])
        self.assertEqual(data["alias"], "local_chat")
        self.assertFalse(data["used_rag"])
        self.assertNotIn("rag private failure", json.dumps(data))
        self.assertNotIn("fallback private failure", json.dumps(data))
        _assert_safe_schema(self, data, expect_error="fallback_alias_failed")
        _assert_fallback_metadata(
            self,
            data,
            reason=FallbackReason.RAG_UNAVAILABLE,
        )

    async def test_debug_failure_includes_exception_class_only(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise RuntimeError("sensitive message must not appear")

        result = await run_local_agent.run_agent(
            question="pergunta",
            debug=True,
            chat_call=chat_call,
        )
        data = result.to_json_dict()

        self.assertEqual(data["error_category"], "chat_unavailable:RuntimeError")
        self.assertNotIn("sensitive message", json.dumps(data))

    async def test_fallback_debug_failure_includes_exception_class_only(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise RuntimeError("fallback sensitive message")

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError("rag sensitive message")

        result = await run_local_agent.run_agent(
            question="pergunta",
            use_rag=True,
            debug=True,
            chat_call=chat_call,
            rag_call=rag_call,
        )
        data = result.to_json_dict()

        self.assertEqual(data["error_category"], "fallback_alias_failed:RuntimeError")
        self.assertNotIn("fallback sensitive message", json.dumps(data))
        self.assertNotIn("rag sensitive message", json.dumps(data))

    async def test_remote_provider_is_never_called(self) -> None:
        source = inspect.getsource(run_local_agent)

        for forbidden in ("openai", "anthropic", "gemini", "openrouter"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())

    async def test_token_estimate_consistency(self) -> None:
        for question in ("", " ", "a", "abcd", "abcde", "Olá, decisão local.", "x" * 100):
            with self.subTest(question=question):
                result = await run_local_agent.run_agent(question=question, dry_run=True)
                self.assertIsInstance(result.estimated_remote_tokens_avoided, int)
                self.assertGreaterEqual(result.estimated_remote_tokens_avoided, 0)

    def test_prompt_token_estimate_boundaries(self) -> None:
        self.assertEqual(run_local_agent._estimate_prompt_token_count(""), 1)
        self.assertEqual(run_local_agent._estimate_prompt_token_count("   "), 1)
        self.assertEqual(run_local_agent._estimate_prompt_token_count("a"), 1)
        self.assertEqual(run_local_agent._estimate_prompt_token_count("abcd"), 1)
        self.assertEqual(run_local_agent._estimate_prompt_token_count("abcde"), 2)
        self.assertGreaterEqual(
            run_local_agent._estimate_prompt_token_count("Olá, ação local."),
            1,
        )

    def test_render_result_contracts(self) -> None:
        result = run_local_agent.AgentRunResult(
            answer="answer",
            route="local",
            alias="local_chat",
            used_rag=False,
            latency_ms=1.0,
            decision_id="decision-id",
            estimated_remote_tokens_avoided=10,
        )

        self.assertEqual(
            run_local_agent.render_result(result, output="text", show_metadata=False),
            "answer",
        )
        with_metadata = run_local_agent.render_result(
            result,
            output="text",
            show_metadata=True,
        )
        self.assertIn("metadata=", with_metadata)
        self.assertNotIn('"answer"', with_metadata)
        data = json.loads(
            run_local_agent.render_result(
                result,
                output="json",
                show_metadata=False,
            )
        )
        _assert_safe_schema(self, data)

    def test_real_routing_policy_config_remains_local_only_when_available(self) -> None:
        policy = load_routing_policy()

        self.assertFalse(policy.remote_enabled)
        self.assertEqual(policy.allowed_remote_providers, ())
        self.assertIn(policy.per_request_token_limit, (0, None))

    async def test_fake_blocked_decision_preserves_schema(self) -> None:
        blocked = RouterDecision(
            decision_id="blocked-decision",
            timestamp_utc="2026-05-02T00:00:00Z",
            route=RouteDecisionKind.BLOCKED,
            reason=RouteBlockReason.BUDGET_EXCEEDED.value,
            risk_level=TaskRiskLevel.LOW,
            token_budget_class=TokenBudgetClass.TINY,
            remote_allowed=False,
            remote_candidate_provider=None,
            requires_sanitization=False,
            estimated_prompt_tokens=1,
            estimated_completion_tokens=1,
            estimated_remote_tokens=2,
            estimated_remote_tokens_avoided=2,
        )

        def fake_decide(**_kwargs: object) -> RouterDecision:
            return blocked

        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise AssertionError("chat should not be called")

        with patch("scripts.run_local_agent.decide_route", fake_decide):
            result = await run_local_agent.run_agent(
                question="pergunta",
                chat_call=chat_call,
            )
        data = result.to_json_dict()

        self.assertEqual(data["decision_id"], "blocked-decision")
        self.assertEqual(data["answer"], BLOCKED_ANSWER)
        self.assertEqual(data["latency_ms"], 0.0)
        self.assertEqual(data["fallback_applied"], False)
        self.assertEqual(data["block_reason"], FallbackReason.BUDGET_EXCEEDED.value)
        _assert_safe_schema(self, data, expect_error="blocked")

    async def test_policy_block_unsupported_task_never_fallbacks(self) -> None:
        async def chat_call(
            question: str,
            *,
            alias: str,
            max_tokens: int | None,
            temperature: float | None,
            response_format: Mapping[str, object] | None,
        ) -> str:
            del question, alias, max_tokens, temperature, response_format
            raise AssertionError("chat should not be called")

        result = await run_local_agent.run_agent(
            question="pergunta",
            chat_call=chat_call,
            policy_loader=lambda: RemoteEscalationPolicy(
                blocked_task_types=("agent0_chat",),
            ),
        )
        data = result.to_json_dict()

        self.assertEqual(data["error_category"], "blocked")
        self.assertEqual(data["fallback_applied"], False)
        self.assertEqual(data["block_reason"], FallbackReason.UNSUPPORTED_TASK.value)
        _assert_safe_schema(self, data, expect_error="blocked")

    async def test_successful_fallback_exits_zero(self) -> None:
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

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError("private")

        with (
            patch("scripts.run_local_agent._call_chat_alias", chat_call),
            patch("scripts.run_local_agent._call_rag", rag_call),
            patch("sys.stdout.write") as write_mock,
        ):
            exit_code = await run_local_agent.main_async(["pergunta", "--rag"])

        self.assertEqual(exit_code, 0)
        rendered = write_mock.call_args.args[0]
        self.assertIn("fallback answer", rendered)

    async def test_policy_block_exits_nonzero(self) -> None:
        with (
            patch(
                "scripts.run_local_agent._safe_policy",
                lambda: RemoteEscalationPolicy(per_request_token_limit=1),
            ),
            patch("sys.stdout.write"),
        ):
            exit_code = await run_local_agent.main_async(["pergunta"])

        self.assertNotEqual(exit_code, 0)

    async def test_fallback_event_is_safe_and_emitted_only_on_fallback(self) -> None:
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

        async def rag_call(
            question: str,
            *,
            max_tokens: int | None,
            temperature: float | None,
        ) -> str:
            del question, max_tokens, temperature
            raise RuntimeError("private prompt should not leak")

        with patch("scripts.run_local_agent.logger.bind", fake_bind):
            await run_local_agent.run_agent(
                question="pergunta",
                use_rag=True,
                chat_call=chat_call,
                rag_call=rag_call,
            )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event"], "agent_fallback")
        self.assertEqual(event["fallback_reason"], FallbackReason.RAG_UNAVAILABLE.value)
        self.assertEqual(event["original_alias"], "local_rag")
        self.assertEqual(event["fallback_alias"], "local_chat")
        self.assertTrue(event["fallback_succeeded"])
        self.assertTrue(FORBIDDEN_OUTPUT_KEYS.isdisjoint({key.lower() for key in event}))

    async def test_no_fallback_event_without_fallback(self) -> None:
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
            await run_local_agent.run_agent(question="pergunta", chat_call=chat_call)

        bind_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
