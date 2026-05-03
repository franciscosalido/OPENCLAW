from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.rag.model_residency import (
    ALLOWED_KEEP_ALIVE_VALUES,
    ModelResidencyConfig,
    decide_model_residency,
    load_model_residency_config,
)


class ModelResidencyConfigTests(unittest.TestCase):
    def test_default_config_is_rollback_safe(self) -> None:
        config = ModelResidencyConfig().validated()
        decision = decide_model_residency(config, alias="local_rag")

        self.assertFalse(config.enabled)
        self.assertEqual(config.apply_to_aliases, ("local_rag",))
        self.assertEqual(config.keep_alive, "5m")
        self.assertFalse(decision.enabled)
        self.assertIsNone(decision.keep_alive)
        self.assertFalse(decision.keep_alive_applied)

    def test_keep_alive_allowlist_accepts_expected_values(self) -> None:
        for keep_alive in sorted(ALLOWED_KEEP_ALIVE_VALUES):
            with self.subTest(keep_alive=keep_alive):
                config = ModelResidencyConfig(keep_alive=keep_alive).validated()
                self.assertEqual(config.keep_alive, keep_alive)

    def test_invalid_keep_alive_rejected(self) -> None:
        for keep_alive in ("", " ", "2h", "forever", "5 minutes"):
            with self.subTest(keep_alive=keep_alive):
                with self.assertRaises(ValueError):
                    ModelResidencyConfig(keep_alive=keep_alive).validated()

    def test_apply_to_aliases_accepts_only_local_rag(self) -> None:
        config = ModelResidencyConfig(apply_to_aliases=("local_rag",)).validated()
        self.assertEqual(config.apply_to_aliases, ("local_rag",))

        with self.assertRaises(ValueError):
            ModelResidencyConfig(apply_to_aliases=("local_chat",)).validated()

    def test_enabled_local_rag_applies_keep_alive(self) -> None:
        decision = decide_model_residency(
            ModelResidencyConfig(enabled=True, keep_alive="5m").validated(),
            alias="local_rag",
        )

        self.assertTrue(decision.enabled)
        self.assertEqual(decision.keep_alive, "5m")
        self.assertTrue(decision.keep_alive_applied)

    def test_enabled_non_rag_alias_is_not_applied(self) -> None:
        decision = decide_model_residency(
            ModelResidencyConfig(enabled=True, keep_alive="5m").validated(),
            alias="local_chat",
        )

        self.assertFalse(decision.enabled)
        self.assertIsNone(decision.keep_alive)

    def test_keep_alive_zero_is_forwardable_when_enabled(self) -> None:
        decision = decide_model_residency(
            ModelResidencyConfig(enabled=True, keep_alive="0").validated(),
            alias="local_rag",
        )

        self.assertTrue(decision.keep_alive_applied)
        self.assertEqual(decision.keep_alive, "0")

    def test_load_model_residency_config_reads_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(
                """
rag:
  model_residency:
    enabled: true
    apply_to_aliases:
      - local_rag
    keep_alive: "10m"
""",
                encoding="utf-8",
            )

            config = load_model_residency_config(path)

        self.assertTrue(config.enabled)
        self.assertEqual(config.apply_to_aliases, ("local_rag",))
        self.assertEqual(config.keep_alive, "10m")

    def test_load_model_residency_config_validates_at_load_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(
                """
rag:
  model_residency:
    enabled: true
    apply_to_aliases:
      - local_rag
    keep_alive: "2h"
""",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_model_residency_config(path)


if __name__ == "__main__":
    unittest.main()
