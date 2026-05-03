from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.rag.generation_budget import (
    GenerationBudgetConfig,
    decide_generation_budget,
    load_generation_budget_config,
)


class GenerationBudgetConfigTests(unittest.TestCase):
    def test_default_config_is_rollback_safe(self) -> None:
        config = GenerationBudgetConfig().validated()
        decision = decide_generation_budget(config, alias="local_rag")

        self.assertFalse(config.enabled)
        self.assertEqual(config.apply_to_aliases, ("local_rag",))
        self.assertEqual(config.max_tokens, 768)
        self.assertFalse(config.enforce_conciseness)
        self.assertFalse(decision.enabled)
        self.assertIsNone(decision.max_tokens)
        self.assertIsNone(decision.conciseness_instruction)

    def test_enabled_local_rag_applies_token_cap(self) -> None:
        decision = decide_generation_budget(
            GenerationBudgetConfig(enabled=True, max_tokens=512),
            alias="local_rag",
        )

        self.assertTrue(decision.enabled)
        self.assertEqual(decision.max_tokens, 512)
        self.assertTrue(decision.max_tokens_applied)

    def test_enabled_non_rag_alias_is_not_applied(self) -> None:
        decision = decide_generation_budget(
            GenerationBudgetConfig(enabled=True, max_tokens=512),
            alias="local_chat",
        )

        self.assertFalse(decision.enabled)
        self.assertIsNone(decision.max_tokens)

    def test_none_max_tokens_disables_forwarded_cap(self) -> None:
        decision = decide_generation_budget(
            GenerationBudgetConfig(enabled=True, max_tokens=None),
            alias="local_rag",
        )

        self.assertTrue(decision.enabled)
        self.assertIsNone(decision.max_tokens)
        self.assertFalse(decision.max_tokens_applied)

    def test_conciseness_instruction_preserves_citation_and_insufficient_context(self) -> None:
        decision = decide_generation_budget(
            GenerationBudgetConfig(
                enabled=True,
                enforce_conciseness=True,
                target_sentences_min=3,
                target_sentences_max=6,
            ),
            alias="local_rag",
        )

        self.assertTrue(decision.conciseness_instruction_applied)
        assert decision.conciseness_instruction is not None
        self.assertIn("3 a 6 frases", decision.conciseness_instruction)
        self.assertIn("citacoes", decision.conciseness_instruction)
        self.assertIn("contexto for insuficiente", decision.conciseness_instruction)

    def test_validation_rejects_invalid_max_tokens(self) -> None:
        with self.assertRaises(ValueError):
            GenerationBudgetConfig(max_tokens=0).validated()

    def test_validation_rejects_invalid_sentence_bounds(self) -> None:
        with self.assertRaises(ValueError):
            GenerationBudgetConfig(target_sentences_min=0).validated()
        with self.assertRaises(ValueError):
            GenerationBudgetConfig(
                target_sentences_min=7,
                target_sentences_max=6,
            ).validated()

    def test_validation_rejects_non_local_rag_alias(self) -> None:
        with self.assertRaises(ValueError):
            GenerationBudgetConfig(apply_to_aliases=("local_chat",)).validated()

    def test_load_generation_budget_config_reads_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(
                """
rag:
  generation_budget:
    enabled: true
    apply_to_aliases:
      - local_rag
    max_tokens: 640
    enforce_conciseness: true
    target_sentences_min: 2
    target_sentences_max: 5
""",
                encoding="utf-8",
            )

            config = load_generation_budget_config(path)

        self.assertTrue(config.enabled)
        self.assertEqual(config.apply_to_aliases, ("local_rag",))
        self.assertEqual(config.max_tokens, 640)
        self.assertTrue(config.enforce_conciseness)
        self.assertEqual(config.target_sentences_min, 2)
        self.assertEqual(config.target_sentences_max, 5)


if __name__ == "__main__":
    unittest.main()
