from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from backend.agent0.domain_routing import load_domain_routing_config


REPO_ROOT = Path(__file__).resolve().parents[2]
RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"


class DomainRoutingConfigTests(unittest.TestCase):
    def test_thresholds_loaded_from_rag_config_yaml(self) -> None:
        config = load_domain_routing_config(RAG_CONFIG)

        self.assertEqual(config.retrieval_score_min, 0.75)
        self.assertEqual(config.escalate_to_think_below, 0.45)
        self.assertEqual(config.p95_routing_budget_ms, 100.0)
        self.assertEqual(config.citation_weight, 0.2)
        self.assertIn("valuation", config.domain_rules)

    def test_invalid_threshold_order_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(
                yaml.safe_dump(
                    _config_with_domain_routing(
                        retrieval_score_min=0.4,
                        escalate_to_think_below=0.5,
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_domain_routing_config(path)

    def test_regex_compile_failure_rejected(self) -> None:
        config = _config_with_domain_routing()
        config["agent0"]["domain_routing"]["domain_rules"]["internal"]["regex"] = ["["]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(yaml.safe_dump(config), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_domain_routing_config(path)

    def test_invalid_collection_rejected(self) -> None:
        config = _config_with_domain_routing()
        config["agent0"]["domain_routing"]["domain_rules"]["internal"][
            "collection_name"
        ] = "openclaw_knowledge"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rag_config.yaml"
            path.write_text(yaml.safe_dump(config), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_domain_routing_config(path)


def _config_with_domain_routing(
    *,
    retrieval_score_min: float = 0.75,
    escalate_to_think_below: float = 0.45,
) -> dict[str, Any]:
    return {
        "agent0": {
            "domain_routing": {
                "retrieval_score_min": retrieval_score_min,
                "escalate_to_think_below": escalate_to_think_below,
                "p95_routing_budget_ms": 100.0,
                "citation_weight": 0.2,
                "domain_rules": {
                    "internal": {
                        "corpus": "internal",
                        "collection_name": "openclaw_internal",
                        "keywords": ["gw-07"],
                        "regex": [r"\bgw-?\d+\b"],
                    },
                    "macroeconomia": {
                        "corpus": "financial",
                        "collection_name": "openclaw_financial",
                        "keywords": ["selic"],
                        "regex": [r"\bselic\b"],
                    },
                },
            }
        }
    }


if __name__ == "__main__":
    unittest.main()
