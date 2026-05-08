from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from backend.agent0.golden_questions import Citation
from backend.agent0.openclaw import Answer, OpenClaw, assert_answer_sanitized


class OpenClawApiTests(unittest.TestCase):
    def test_ask_validates_non_empty_question(self) -> None:
        api = OpenClaw(ask_backend=_fake_backend)

        with self.assertRaises(ValueError):
            api.ask("   ")

    def test_ask_returns_safe_answer_with_citation(self) -> None:
        api = OpenClaw(ask_backend=_fake_backend)

        result = api.ask("qual o estado atual do GW-07?")

        self.assertEqual(result.answer, "Resposta local sintética.")
        self.assertEqual(result.route, "local_rag")
        self.assertEqual(result.corpus, "internal")
        self.assertTrue(result.citation_present)
        self.assertEqual(result.citations[0].doc_id, "internal_current_state")
        assert_answer_sanitized(result.to_dict())

    def test_answer_is_frozen_and_safe(self) -> None:
        answer = _answer()

        with self.assertRaises(FrozenInstanceError):
            answer.answer = "mutated"  # type: ignore[misc]

        data = answer.to_dict()
        self.assertNotIn("prompt", data)
        self.assertNotIn("chunks", data)
        self.assertNotIn("payload", data)

    def test_answer_sanitizer_rejects_forbidden_keys(self) -> None:
        with self.assertRaises(ValueError):
            assert_answer_sanitized({"prompt": "redacted"})


def _fake_backend(question: str, decision: object) -> Answer:
    del question, decision
    return _answer()


def _answer() -> Answer:
    return Answer(
        answer="Resposta local sintética.",
        citations=(
            Citation(
                question_id="iq-001",
                source_id="internal-current-state-001",
                doc_id="internal_current_state",
                chunk_id="internal_current_state#0",
                corpus="internal",
                collection_name="openclaw_internal",
                origin_path="docs/current_state.md",
                score=1.0,
                rank=1,
                retrieval_mode="fake",
                chunk_index=0,
            ),
        ),
        route="local_rag",
        corpus="internal",
        latency_ms=1.0,
        citation_present=True,
        fallback_reason=None,
        error_category=None,
    )


if __name__ == "__main__":
    unittest.main()
