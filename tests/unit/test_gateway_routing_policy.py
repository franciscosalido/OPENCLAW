from __future__ import annotations

import inspect
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import yaml

from backend.gateway import routing_policy
from backend.gateway.routing_policy import (
    RemoteEscalationPolicy,
    RouteBlockReason,
    RouteDecisionKind,
    TaskRiskLevel,
    TokenBudgetClass,
    TokenEconomyRecord,
    build_token_economy_record,
    decide_route,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"
FORBIDDEN_SERIALIZED_KEYS = {
    "query",
    "prompt",
    "answer",
    "chunks",
    "vectors",
    "payload",
    "api_key",
    "authorization",
    "secret",
    "token_value",
    "password",
    "headers",
}


def _routing_config() -> dict[str, Any]:
    raw = yaml.safe_load(RAG_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    gateway = raw["gateway"]
    assert isinstance(gateway, dict)
    routing = gateway["routing"]
    assert isinstance(routing, dict)
    return cast(dict[str, Any], routing)


class GatewayRoutingPolicyTests(unittest.TestCase):
    def test_default_config_disables_remote_providers(self) -> None:
        config = _routing_config()

        self.assertFalse(config["remote_enabled"])
        self.assertEqual(config["default_route"], "local")
        self.assertEqual(config["allowed_remote_providers"], [])
        self.assertEqual(config["per_request_token_limit"], 0)

    def test_default_policy_disables_remote(self) -> None:
        policy = RemoteEscalationPolicy()

        self.assertFalse(policy.remote_enabled)
        self.assertEqual(policy.allowed_remote_providers, ())

    def test_small_low_risk_task_routes_local(self) -> None:
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=120,
            estimated_completion_tokens=80,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        self.assertEqual(decision.route, RouteDecisionKind.LOCAL)
        self.assertEqual(decision.reason, "local_first_default")
        self.assertEqual(decision.risk_level, TaskRiskLevel.LOW)
        self.assertEqual(decision.token_budget_class, TokenBudgetClass.TINY)
        self.assertFalse(decision.remote_allowed)
        self.assertEqual(decision.estimated_remote_tokens_avoided, 200)

    def test_high_value_task_is_blocked_when_remote_disabled(self) -> None:
        decision = decide_route(
            task_type="portfolio_review",
            estimated_prompt_tokens=2_000,
            estimated_completion_tokens=800,
            contains_sensitive_context=False,
            high_value_task=True,
            policy=RemoteEscalationPolicy(remote_enabled=False),
        )

        self.assertEqual(decision.route, RouteDecisionKind.BLOCKED)
        self.assertEqual(decision.reason, RouteBlockReason.REMOTE_DISABLED.value)
        self.assertFalse(decision.remote_allowed)
        self.assertTrue(decision.requires_sanitization)
        self.assertEqual(decision.estimated_remote_tokens_avoided, 2_800)

    def test_high_value_task_can_be_remote_candidate_when_explicitly_enabled(self) -> None:
        decision = decide_route(
            task_type="architecture_review",
            estimated_prompt_tokens=2_000,
            estimated_completion_tokens=1_000,
            contains_sensitive_context=False,
            high_value_task=True,
            policy=RemoteEscalationPolicy(
                remote_enabled=True,
                allowed_remote_providers=("future_provider",),
            ),
        )

        self.assertEqual(decision.route, RouteDecisionKind.REMOTE_CANDIDATE)
        self.assertTrue(decision.remote_allowed)
        self.assertEqual(decision.remote_candidate_provider, "future_provider")
        self.assertIsNone(decision.estimated_remote_tokens_avoided)

    def test_sensitive_context_never_routes_remote(self) -> None:
        decision = decide_route(
            task_type="question_answering",
            estimated_prompt_tokens=600,
            estimated_completion_tokens=300,
            contains_sensitive_context=True,
            high_value_task=True,
            policy=RemoteEscalationPolicy(
                remote_enabled=True,
                allowed_remote_providers=("future_provider",),
            ),
        )

        self.assertEqual(decision.route, RouteDecisionKind.LOCAL)
        self.assertEqual(decision.reason, RouteBlockReason.SENSITIVE_CONTEXT.value)
        self.assertFalse(decision.remote_allowed)
        self.assertIsNone(decision.remote_candidate_provider)
        self.assertTrue(decision.requires_sanitization)

    def test_budget_exceeded_blocks(self) -> None:
        decision = decide_route(
            task_type="large_review",
            estimated_prompt_tokens=5_000,
            estimated_completion_tokens=2_000,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(per_request_token_limit=1_000),
        )

        self.assertEqual(decision.route, RouteDecisionKind.BLOCKED)
        self.assertEqual(decision.reason, RouteBlockReason.BUDGET_EXCEEDED.value)
        self.assertEqual(decision.token_budget_class, TokenBudgetClass.BLOCKED)
        self.assertEqual(decision.estimated_remote_tokens_avoided, 7_000)

    def test_unsupported_task_blocks(self) -> None:
        decision = decide_route(
            task_type="trade_execution",
            estimated_prompt_tokens=20,
            estimated_completion_tokens=20,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        self.assertEqual(decision.route, RouteDecisionKind.BLOCKED)
        self.assertEqual(decision.reason, RouteBlockReason.UNSUPPORTED_TASK.value)

    def test_decision_is_frozen(self) -> None:
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=10,
            estimated_completion_tokens=10,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        with self.assertRaises(FrozenInstanceError):
            decision.reason = "changed"  # type: ignore[misc]

    def test_decision_to_log_dict_excludes_forbidden_fields(self) -> None:
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=10,
            estimated_completion_tokens=10,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        data = decision.to_log_dict()

        self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint({key.lower() for key in data}))
        self.assertEqual(data["route"], "local")
        self.assertEqual(data["risk_level"], "low")

    def test_token_economy_record_estimates_remote_tokens_avoided(self) -> None:
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=100,
            estimated_completion_tokens=50,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        record = build_token_economy_record(decision)
        data = record.to_log_dict()

        self.assertIsInstance(record, TokenEconomyRecord)
        self.assertEqual(record.local_tokens_estimated, 150)
        self.assertEqual(record.remote_tokens_avoided_estimated, 150)
        self.assertEqual(data["cost_estimate_mode"], "estimated_not_billed")
        self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint({key.lower() for key in data}))

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            RemoteEscalationPolicy(monthly_budget_usd=-1.0)
        with self.assertRaises(ValueError):
            RemoteEscalationPolicy(per_request_token_limit=-1)
        with self.assertRaises(ValueError):
            decide_route(
                task_type="summary",
                estimated_prompt_tokens=-1,
                estimated_completion_tokens=1,
                contains_sensitive_context=False,
                high_value_task=False,
                policy=RemoteEscalationPolicy(),
            )

    def test_module_does_not_read_secrets_or_call_network(self) -> None:
        source = inspect.getsource(routing_policy)

        for forbidden in ("os.environ", "getenv", "httpx", "requests", "urllib", "socket"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
