from __future__ import annotations

import unittest

from backend.agent0.domain_routing import (
    FakeConfidenceScorer,
    SystemState,
    load_domain_routing_config,
    route,
)
from backend.agent0.routing_report import (
    ROUTING_FORBIDDEN_KEYS,
    assert_routing_report_sanitized,
    build_routing_report,
)


class DomainRoutingReportTests(unittest.TestCase):
    def test_report_contains_no_forbidden_keys(self) -> None:
        config = load_domain_routing_config()
        decisions = (
            route(
                "qual o estado atual do GW-07?",
                SystemState(qdrant_available=True),
                config,
                FakeConfidenceScorer(default_score=1.0),
            ),
            route(
                "como calcular o EBITDA?",
                SystemState(qdrant_available=True),
                config,
                FakeConfidenceScorer(default_score=1.0),
            ),
        )

        report = build_routing_report(
            decisions=decisions,
            passed=2,
            failed=0,
            golden_accuracy=1.0,
        )

        assert_routing_report_sanitized(report)
        self.assertTrue(_forbidden_keys_absent(report, ROUTING_FORBIDDEN_KEYS))
        self.assertEqual(report["total_decisions"], 2)
        self.assertEqual(report["coverage"], 1.0)
        self.assertEqual(report["golden_accuracy"], 1.0)
        self.assertIn("local_rag", report["route_counts"])

    def test_report_sanitizer_rejects_forbidden_keys(self) -> None:
        with self.assertRaises(ValueError):
            assert_routing_report_sanitized({"query": "redacted"})
        with self.assertRaises(ValueError):
            assert_routing_report_sanitized({"payload": {"safe": True}})


def _forbidden_keys_absent(value: object, forbidden: frozenset[str]) -> bool:
    if isinstance(value, dict):
        return all(
            key not in forbidden and _forbidden_keys_absent(nested, forbidden)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return all(_forbidden_keys_absent(item, forbidden) for item in value)
    return True


if __name__ == "__main__":
    unittest.main()
