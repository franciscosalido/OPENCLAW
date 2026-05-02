from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.gateway.routing_policy import (
    RemoteEscalationPolicy,
    RouterDecision,
    RoutingDecisionLogger,
    build_token_economy_record,
    decide_route,
)


FORBIDDEN_SERIALIZED_KEYS = {
    "query",
    "question",
    "prompt",
    "answer",
    "response",
    "chunk",
    "chunks",
    "vector",
    "vectors",
    "embedding",
    "payload",
    "qdrant_payload",
    "portfolio",
    "carteira",
    "api_key",
    "authorization",
    "secret",
    "token_value",
    "password",
    "headers",
}


def _decision() -> RouterDecision:
    return decide_route(
        task_type="summary",
        estimated_prompt_tokens=100,
        estimated_completion_tokens=50,
        contains_sensitive_context=False,
        high_value_task=False,
        policy=RemoteEscalationPolicy(),
    )


class RoutingDecisionLoggerTests(unittest.TestCase):
    def test_disabled_logger_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = RoutingDecisionLogger(
                Path(tmpdir) / "routing_decisions",
                enabled=False,
            )

            result = logger.append(_decision())

            self.assertIsNone(result)
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_logger_writes_exactly_one_jsonl_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = RoutingDecisionLogger(
                Path(tmpdir) / "routing_decisions",
                rotate_daily=False,
            )

            path = logger.append(_decision())

            self.assertIsNotNone(path)
            assert path is not None
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertEqual(data["route"], "local")
            self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint(set(data)))

    def test_daily_rotation_filename_includes_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = RoutingDecisionLogger(Path(tmpdir) / "routing_decisions")

            path = logger.append(_decision())

            self.assertIsNotNone(path)
            assert path is not None
            self.assertRegex(
                path.name,
                r"routing_decisions_\d{4}-\d{2}-\d{2}\.jsonl",
            )

    def test_logger_can_append_token_economy_record(self) -> None:
        decision = _decision()
        record = build_token_economy_record(decision)

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = RoutingDecisionLogger(
                Path(tmpdir) / "routing_decisions",
                rotate_daily=False,
            )

            path = logger.append(record)

            self.assertIsNotNone(path)
            assert path is not None
            data = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(data["cost_estimate_mode"], "estimated_not_billed")
            self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint(set(data)))


if __name__ == "__main__":
    unittest.main()
