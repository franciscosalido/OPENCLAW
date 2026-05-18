"""Tests for the PR-04B Qwen3 shadow collection contract."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

from backend.rag.embedding_config import EmbeddingProfileConfig
from backend.rag.embedding_metadata import compute_profile_fingerprint
from backend.rag.shadow_collection import (
    PROTECTED_COLLECTIONS,
    QWEN3_SHADOW_COLLECTION,
    SHADOW_COLLECTIONS,
    VectorPayloadMetadata,
    assert_collection_is_shadow,
)


def _qwen3_profile() -> EmbeddingProfileConfig:
    return EmbeddingProfileConfig(
        provider="sentence_transformers",
        model="Qwen/Qwen3-Embedding-8B",
        model_family="qwen3",
        version="v1",
        dimensions=4096,
        effective_dimensions=None,
        mrl_supported=True,
        context_length=32768,
        distance="cosine",
        normalized=True,
        instruction_aware=True,
        query_instruction="Given a financial query, retrieve relevant passages.",
        document_instruction=None,
        profile_fingerprint=None,
    )


class ShadowCollectionContractTests(unittest.TestCase):
    """Shadow collection and payload metadata tests."""

    def test_protected_collections_cannot_be_shadow(self) -> None:
        for collection_name in sorted(PROTECTED_COLLECTIONS):
            with self.subTest(collection_name=collection_name):
                with self.assertRaisesRegex(ValueError, "protected"):
                    assert_collection_is_shadow(collection_name)

    def test_shadow_collection_is_accepted(self) -> None:
        assert_collection_is_shadow(QWEN3_SHADOW_COLLECTION)

    def test_unknown_collection_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a declared shadow collection"):
            assert_collection_is_shadow("custom_qwen3_collection")

    def test_collection_name_rejects_null_bytes(self) -> None:
        with self.assertRaisesRegex(ValueError, "null bytes"):
            assert_collection_is_shadow(f"{QWEN3_SHADOW_COLLECTION}\x00")

    def test_shadow_collection_namespace_is_exact(self) -> None:
        self.assertEqual(
            SHADOW_COLLECTIONS,
            frozenset({"quimera_knowledge_qwen3_dense_v1"}),
        )

    def test_payload_metadata_from_profile(self) -> None:
        profile = _qwen3_profile()
        timestamp = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

        metadata = VectorPayloadMetadata.from_profile(profile, indexed_at=timestamp)
        payload = metadata.to_payload()

        self.assertEqual(metadata.model, "Qwen/Qwen3-Embedding-8B")
        self.assertEqual(metadata.model_family, "qwen3")
        self.assertEqual(metadata.dimensions, 4096)
        self.assertEqual(metadata.effective_dimensions, 4096)
        self.assertEqual(metadata.distance, "cosine")
        self.assertTrue(metadata.normalized)
        self.assertEqual(metadata.provider, "sentence_transformers")
        self.assertEqual(
            metadata.profile_fingerprint,
            compute_profile_fingerprint(profile),
        )
        self.assertEqual(payload["indexed_at"], "2026-05-17T12:00:00+00:00")

    def test_payload_metadata_uses_effective_dimensions_when_present(self) -> None:
        profile = _qwen3_profile().model_copy(update={"effective_dimensions": 1024})

        metadata = VectorPayloadMetadata.from_profile(profile)

        self.assertEqual(metadata.dimensions, 4096)
        self.assertEqual(metadata.effective_dimensions, 1024)

    def test_payload_metadata_rejects_non_positive_effective_dimensions(self) -> None:
        invalid_profile = cast(
            EmbeddingProfileConfig,
            SimpleNamespace(dimensions=0, effective_dimensions=None),
        )

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            VectorPayloadMetadata.from_profile(invalid_profile)


if __name__ == "__main__":
    unittest.main()
