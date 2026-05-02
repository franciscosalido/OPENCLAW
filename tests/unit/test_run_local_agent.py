from __future__ import annotations

import json
import inspect
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from backend.gateway.routing_policy import (
    RemoteEscalationPolicy,
    RouterDecision,
    decide_route,
)
from scripts import run_local_agent


FORBIDDEN_OUTPUT_KEYS = {
    "query",
    "question",
    "prompt",
    "chunks",
    "chunk_text",
    "vectors",
    "embeddings",
    "payload",
    "qdrant_payload",
    "api_key",
    "authorization",
    "secret",
    "password",
    "headers",
    "raw_response",
    "traceback",
}


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


class RunLocalAgentTests(unittest.IsolatedAsyncioTestCase):
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

        self.assertEqual(result.answer, "Dry run: no model call executed.")
        self.assertEqual(result.alias, "local_chat")

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

        self.assertEqual(
            set(data),
            {
                "answer",
                "route",
                "alias",
                "used_rag",
                "latency_ms",
                "decision_id",
                "estimated_remote_tokens_avoided",
            },
        )
        self.assertTrue(FORBIDDEN_OUTPUT_KEYS.isdisjoint({key.lower() for key in data}))

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

    async def test_rag_unavailable_produces_safe_error_category(self) -> None:
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
            rag_call=rag_call,
        )

        data = result.to_json_dict()
        self.assertEqual(data["error_category"], "rag_unavailable")
        self.assertNotIn("service down", json.dumps(data))

    async def test_remote_provider_is_never_called(self) -> None:
        source = inspect.getsource(run_local_agent)

        for forbidden in ("openai", "anthropic", "gemini", "openrouter"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
