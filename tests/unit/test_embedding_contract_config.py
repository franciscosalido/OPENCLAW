"""Static tests for the Quimera embedding contract configuration."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

from backend.gateway.client import (
    COMPAT_LLM_EMBED_MODEL,
    DEFAULT_LLM_EMBED_MODEL,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_LITELLM_CONFIG = REPO_ROOT / "config" / "litellm_config.yaml"
OPERATIONAL_LITELLM_CONFIG = REPO_ROOT / "infra" / "litellm" / "litellm_config.yaml"
RAG_CONFIG = REPO_ROOT / "config" / "rag_config.yaml"

REQUIRED_METADATA_KEYS = {
    "embedding_provider",
    "embedding_model",
    "embedding_dimensions",
    "embedding_version",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError(f"{path} did not load as a YAML mapping")
    return raw


def _aliases(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    model_list = config.get("model_list")
    if not isinstance(model_list, list):
        raise AssertionError("LiteLLM config is missing model_list")
    aliases: dict[str, dict[str, Any]] = {}
    for item in model_list:
        if not isinstance(item, dict):
            raise AssertionError("LiteLLM model_list item is not a mapping")
        name = item.get("model_name")
        if not isinstance(name, str):
            raise AssertionError("LiteLLM alias is missing model_name")
        aliases[name] = item
    return aliases


class EmbeddingContractConfigTests(unittest.TestCase):
    """Validate static config invariants for the embeddings contract."""

    def test_default_embedding_alias_is_canonical_quimera_alias(self) -> None:
        self.assertEqual(DEFAULT_LLM_EMBED_MODEL, "quimera_embed")
        self.assertEqual(COMPAT_LLM_EMBED_MODEL, "local_embed")

    def test_reference_config_defines_canonical_and_compat_aliases(self) -> None:
        aliases = _aliases(_load_yaml(REFERENCE_LITELLM_CONFIG))

        self.assertIn("quimera_embed", aliases)
        self.assertIn("local_embed", aliases)

    def test_operational_config_defines_canonical_and_compat_aliases(self) -> None:
        aliases = _aliases(_load_yaml(OPERATIONAL_LITELLM_CONFIG))

        self.assertIn("quimera_embed", aliases)
        self.assertIn("local_embed", aliases)

    def test_embedding_aliases_share_same_current_backend(self) -> None:
        for path in (REFERENCE_LITELLM_CONFIG, OPERATIONAL_LITELLM_CONFIG):
            with self.subTest(path=path):
                aliases = _aliases(_load_yaml(path))
                canonical = aliases["quimera_embed"]["litellm_params"]
                compat = aliases["local_embed"]["litellm_params"]

                self.assertEqual(canonical["model"], compat["model"])
                self.assertEqual(canonical["api_base"], compat["api_base"])
                self.assertEqual(canonical["timeout"], compat["timeout"])

    def test_embedding_aliases_remain_local_only(self) -> None:
        for path in (REFERENCE_LITELLM_CONFIG, OPERATIONAL_LITELLM_CONFIG):
            with self.subTest(path=path):
                aliases = _aliases(_load_yaml(path))
                for name in ("quimera_embed", "local_embed"):
                    params = aliases[name]["litellm_params"]
                    combined = str(params).lower()
                    self.assertNotIn("openai", combined)
                    self.assertNotIn("anthropic", combined)
                    self.assertNotIn("gemini", combined)
                    self.assertNotIn("https://", combined)

    def test_rag_config_includes_required_embedding_metadata(self) -> None:
        raw = _load_yaml(RAG_CONFIG)
        embedding = raw["rag"]["embedding"]

        for key in REQUIRED_METADATA_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, embedding)

        self.assertEqual(embedding["embedding_provider"], "ollama")
        self.assertEqual(embedding["embedding_model"], "nomic-embed-text")
        self.assertEqual(embedding["embedding_dimensions"], 768)
        self.assertEqual(embedding["embedding_version"], "local-ollama-current")

    def test_rag_config_records_controlled_gateway_migration_with_rollback(self) -> None:
        raw = _load_yaml(RAG_CONFIG)
        embedding = raw["rag"]["embedding"]

        self.assertEqual(embedding["active_backend"], "gateway_litellm")
        self.assertEqual(
            embedding["embedding_contract"],
            "openai_compatible_v1_embeddings",
        )
        self.assertEqual(embedding["embedding_alias"], "quimera_embed")
        self.assertEqual(embedding["gateway_embedding_alias"], "quimera_embed")
        self.assertEqual(embedding["gateway_compatibility_alias"], "local_embed")
        self.assertEqual(
            embedding["gateway_embedding_status"],
            "controlled_migration_current",
        )
        self.assertEqual(embedding["embedding_backend"], "gateway_litellm_current")
        self.assertEqual(embedding["legacy_embedding_backend"], "direct_ollama")
        self.assertEqual(embedding["max_retries"], 3)
        self.assertEqual(embedding["backoff_seconds"], 1.0)
        self.assertEqual(embedding["max_concurrency"], 4)
        self.assertTrue(embedding["reindex_required_on_model_change"])
        self.assertEqual(embedding["model"], "nomic-embed-text")
        self.assertEqual(embedding["endpoint"], "http://localhost:11434")

    def test_application_facing_embedding_alias_hides_concrete_model(self) -> None:
        self.assertNotIn("nomic", DEFAULT_LLM_EMBED_MODEL)
        self.assertNotIn("ollama/", DEFAULT_LLM_EMBED_MODEL)
        self.assertEqual(DEFAULT_LLM_EMBED_MODEL, "quimera_embed")


if __name__ == "__main__":
    unittest.main()
