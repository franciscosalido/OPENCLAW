from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from backend.agent0.domain_routing import (
    FakeConfidenceScorer,
    RouteDecision,
    SystemState,
    load_domain_routing_config,
    route,
    route_dry_run_p95,
    validate_routing_against_golden_questions,
)


FORBIDDEN_SERIALIZED_KEYS = {
    "query",
    "text",
    "raw_text",
    "answer",
    "prompt",
    "chunks",
    "chunk_text",
    "vectors",
    "embeddings",
    "payload",
    "headers",
    "api_key",
    "authorization",
    "raw_exception",
    "traceback",
    "absolute_path",
    "username",
}


class DomainRoutingTests(unittest.TestCase):
    TOTAL_GOLDEN_QUESTIONS = 14

    def setUp(self) -> None:
        self.config = load_domain_routing_config()
        self.state = SystemState(qdrant_available=True)

    def test_high_confidence_routes_local_rag(self) -> None:
        decision = route(
            "no texto sintetico local de crescimento em valuation, "
            "qual tratamento conceitual do EBITDA aparece?",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=self.config.retrieval_score_min),
        )

        self.assertEqual(decision.route, "local_rag")
        self.assertEqual(decision.corpus, "financial")
        self.assertEqual(decision.collection_name, "openclaw_financial")
        self.assertEqual(decision.reason_code, "retrieval_confident")

    def test_medium_confidence_routes_local_think(self) -> None:
        medium_score = (
            self.config.retrieval_score_min + self.config.escalate_to_think_below
        ) / 2
        decision = route(
            "segundo o documento sintetico local de curva de renda fixa, "
            "quais movimentos de duration precisam ser citados?",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=medium_score),
        )

        self.assertEqual(decision.route, "local_think")
        self.assertEqual(decision.corpus, "financial")
        self.assertEqual(decision.reason_code, "retrieval_uncertain")

    def test_low_confidence_routes_local_chat(self) -> None:
        decision = route(
            "segundo o documento sintetico local de ciclo de juros, "
            "quais fatores explicam a trajetoria hipotetica da Selic?",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=0.01),
        )

        self.assertEqual(decision.route, "local_chat")
        self.assertEqual(decision.corpus, "none")
        self.assertEqual(decision.fallback_reason, "retrieval_low_confidence")

    def test_qdrant_unavailable_routes_local_chat(self) -> None:
        decision = route(
            "no texto sintetico local de crescimento em valuation, "
            "qual tratamento conceitual do EBITDA aparece?",
            SystemState(qdrant_available=False),
            self.config,
            FakeConfidenceScorer(default_score=1.0),
        )

        self.assertEqual(decision.route, "local_chat")
        self.assertEqual(decision.corpus, "none")
        self.assertEqual(decision.collection_name, "none")
        self.assertEqual(decision.reason_code, "qdrant_unavailable")

    def test_unknown_domain_routes_local_chat(self) -> None:
        decision = route(
            "pergunta generica sem dominio mapeado",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=1.0),
        )

        self.assertEqual(decision.route, "local_chat")
        self.assertEqual(decision.domain, "unknown")
        self.assertEqual(decision.reason_code, "no_domain_match")

    def test_fq_prefix_without_keyword_preserves_financial_route(self) -> None:
        decision = route(
            "pergunta sintetica sem termos financeiros mapeados",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=self.config.retrieval_score_min),
            question_id="fq-999",
        )

        self.assertEqual(decision.route, "local_rag")
        self.assertEqual(decision.domain, "unknown")
        self.assertEqual(decision.corpus, "financial")
        self.assertEqual(decision.collection_name, "openclaw_financial")
        self.assertEqual(decision.reason_code, "retrieval_confident")

    def test_low_confidence_fq_prefix_without_keyword_keeps_financial_context(self) -> None:
        decision = route(
            "pergunta sintetica sem termos financeiros mapeados",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=0.01),
            question_id="fq-999",
        )

        self.assertEqual(decision.route, "local_chat")
        self.assertEqual(decision.domain, "unknown")
        self.assertEqual(decision.corpus, "financial")
        self.assertEqual(decision.collection_name, "openclaw_financial")
        self.assertEqual(decision.fallback_reason, "retrieval_low_confidence")

    def test_route_decision_is_frozen(self) -> None:
        decision = route(
            "qual o estado atual do GW-07?",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=1.0),
        )

        with self.assertRaises(FrozenInstanceError):
            decision.route = "local_chat"  # type: ignore[misc]

    def test_route_decision_to_dict_is_allowlisted(self) -> None:
        decision = route(
            "qual o estado atual do GW-07?",
            self.state,
            self.config,
            FakeConfidenceScorer(default_score=1.0),
        )

        data = decision.to_dict()

        self.assertTrue(FORBIDDEN_SERIALIZED_KEYS.isdisjoint(data))
        self.assertEqual(
            set(data),
            {
                "route",
                "corpus",
                "domain",
                "collection_name",
                "confidence_score",
                "threshold_used",
                "reason_code",
                "latency_ms",
                "routing_mode",
            },
        )

    def test_golden_question_gate_routes_all_covered_questions(self) -> None:
        result = validate_routing_against_golden_questions(config=self.config)

        self.assertEqual(result.accuracy, 1.0)
        self.assertEqual(result.total_questions, self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(result.passed, self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.failed_question_ids, ())
        self.assertTrue(
            all(decision.route == "local_rag" for decision in result.decisions)
        )

    def test_golden_question_gate_reports_failed_question_ids(self) -> None:
        result = validate_routing_against_golden_questions(
            config=self.config,
            scorer=FakeConfidenceScorer(
                default_score=self.config.retrieval_score_min,
                scores_by_domain={"valuation": 0.01},
            ),
        )

        self.assertEqual(result.total_questions, self.TOTAL_GOLDEN_QUESTIONS)
        self.assertEqual(result.passed, 11)
        self.assertEqual(result.failed, 3)
        self.assertEqual(result.failed_question_ids, ("fq-004", "fq-005", "fq-006"))

    def test_p95_routing_dry_run_under_config_budget(self) -> None:
        p95 = route_dry_run_p95(config=self.config)

        self.assertLess(p95, self.config.p95_routing_budget_ms)


if __name__ == "__main__":
    unittest.main()
