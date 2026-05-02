from __future__ import annotations

import unittest

from backend.gateway.routing_policy import (
    RemoteEscalationPolicy,
    TokenBudgetAccumulator,
    build_token_economy_record,
    decide_route,
)


class TokenBudgetAccumulatorTests(unittest.TestCase):
    def test_add_decision_and_total(self) -> None:
        accumulator = TokenBudgetAccumulator()
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=100,
            estimated_completion_tokens=50,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )

        accumulator.add(decision)

        self.assertEqual(
            accumulator.total(),
            {
                "estimated_prompt_tokens": 100,
                "estimated_completion_tokens": 50,
                "estimated_remote_tokens": 150,
                "estimated_remote_tokens_avoided": 150,
            },
        )

    def test_add_token_economy_record_and_reset(self) -> None:
        accumulator = TokenBudgetAccumulator()
        decision = decide_route(
            task_type="summary",
            estimated_prompt_tokens=100,
            estimated_completion_tokens=50,
            contains_sensitive_context=False,
            high_value_task=False,
            policy=RemoteEscalationPolicy(),
        )
        record = build_token_economy_record(decision)

        accumulator.add(record)
        self.assertEqual(accumulator.total()["estimated_remote_tokens"], 150)
        self.assertEqual(accumulator.total()["estimated_remote_tokens_avoided"], 150)

        accumulator.reset()

        self.assertEqual(
            accumulator.total(),
            {
                "estimated_prompt_tokens": 0,
                "estimated_completion_tokens": 0,
                "estimated_remote_tokens": 0,
                "estimated_remote_tokens_avoided": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
