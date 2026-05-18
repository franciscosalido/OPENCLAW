"""Unit tests for the dense embedder provider registry contract."""

from __future__ import annotations

import unittest

from backend.rag.embedder_registry import get_registry, register
from backend.rag.embedder_protocol import DenseEmbedder
from backend.rag.embedding_config import EmbeddingProfileConfig
from tests.fakes.fake_qwen3_embedder import FakeQwen3Embedder


def _factory(profile: EmbeddingProfileConfig) -> DenseEmbedder:
    _ = profile
    return FakeQwen3Embedder()


class EmbedderRegistryTests(unittest.TestCase):
    """Registry tests that avoid loading real embedding models."""

    def test_get_registry_returns_read_only_snapshot(self) -> None:
        provider = "rc01_snapshot_provider"
        before = get_registry()

        register(provider, _factory)
        after = get_registry()

        self.assertNotIn(provider, before)
        self.assertIn(provider, after)
        with self.assertRaises(TypeError):
            after["another_provider"] = _factory  # type: ignore[index]
        self.assertNotIn("another_provider", get_registry())

    def test_register_rejects_duplicate_provider(self) -> None:
        provider = "rc01_duplicate_provider"

        register(provider, _factory)

        with self.assertRaisesRegex(ValueError, "already registered"):
            register(provider, _factory)

    def test_register_normalizes_provider_names(self) -> None:
        register("  RC01_NORMALIZED_PROVIDER  ", _factory)

        self.assertIn("rc01_normalized_provider", get_registry())

    def test_register_rejects_invalid_provider_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            register("   ", _factory)
        with self.assertRaisesRegex(ValueError, "null bytes"):
            register("bad\x00provider", _factory)


if __name__ == "__main__":
    unittest.main()
