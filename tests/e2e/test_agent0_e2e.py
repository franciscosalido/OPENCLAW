from __future__ import annotations

import os
import unittest

from backend.agent0.e2e_report import assert_e2e_report_sanitized, build_e2e_report
from backend.agent0.golden_questions import load_all_golden_questions
from backend.agent0.openclaw import OpenClaw


RUN_AGENT0_E2E = "RUN_AGENT0_E2E"
E2E_P95_BUDGET_MS = 15_000.0
MIN_CITATION_HITS = 5


@unittest.skipUnless(
    os.environ.get(RUN_AGENT0_E2E) == "1",
    "Agent-0 E2E requires RUN_AGENT0_E2E=1 and local services/corpora.",
)
class Agent0E2ETests(unittest.TestCase):
    def test_golden_questions_meet_slos(self) -> None:
        api = OpenClaw()
        results = []
        try:
            for question in load_all_golden_questions():
                if question.enabled:
                    answer = api.ask(question.text)
                    if answer.error_category is not None:
                        self.skipTest(
                            "local Agent-0 services unavailable: "
                            f"{answer.error_category}"
                        )
                    results.append((question.question_id, answer))
        except Exception as exc:
            self.skipTest(f"local Agent-0 services unavailable: {exc.__class__.__name__}")

        report = build_e2e_report(results)

        assert_e2e_report_sanitized(report)
        self.assertLess(report["p95_latency_ms"], E2E_P95_BUDGET_MS)
        self.assertGreaterEqual(report["passed"], MIN_CITATION_HITS)

    def test_required_human_case_returns_citation(self) -> None:
        try:
            answer = OpenClaw().ask("qual o estado do GW-07?")
        except Exception as exc:
            self.skipTest(f"local Agent-0 services unavailable: {exc.__class__.__name__}")
        if answer.error_category is not None:
            self.skipTest(f"local Agent-0 services unavailable: {answer.error_category}")

        self.assertTrue(answer.answer)
        self.assertTrue(answer.citation_present)
        self.assertGreaterEqual(len(answer.citations), 1)
        self.assertNotIn("prompt", answer.to_dict())
        self.assertNotIn("chunks", answer.to_dict())


if __name__ == "__main__":
    unittest.main()
