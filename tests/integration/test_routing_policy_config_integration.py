from __future__ import annotations

import unittest
from pathlib import Path

from backend.gateway.routing_policy import (
    RemoteEscalationPolicy,
    RouteDecisionKind,
    decide_route,
    load_routing_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"


class RoutingPolicyConfigIntegrationTests(unittest.TestCase):
    def test_load_real_rag_config_keeps_remote_disabled(self) -> None:
        policy = load_routing_policy(RAG_CONFIG)

        self.assertIsInstance(policy, RemoteEscalationPolicy)
        self.assertFalse(policy.remote_enabled)
        self.assertEqual(policy.allowed_remote_providers, ())

    def test_default_config_produces_only_local_or_blocked_decisions(self) -> None:
        policy = load_routing_policy(RAG_CONFIG)
        cases = [
            ("summary", 100, 50, False, False),
            ("portfolio_review", 2_000, 1_000, False, True),
            ("trade_execution", 20, 20, False, False),
        ]

        for task_type, prompt_tokens, completion_tokens, sensitive, high_value in cases:
            with self.subTest(task_type=task_type):
                decision = decide_route(
                    task_type=task_type,
                    estimated_prompt_tokens=prompt_tokens,
                    estimated_completion_tokens=completion_tokens,
                    contains_sensitive_context=sensitive,
                    high_value_task=high_value,
                    policy=policy,
                )
                self.assertIn(
                    decision.route,
                    {RouteDecisionKind.LOCAL, RouteDecisionKind.BLOCKED},
                )
                self.assertFalse(decision.remote_allowed)


if __name__ == "__main__":
    unittest.main()
