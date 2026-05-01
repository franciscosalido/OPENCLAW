from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from loguru import logger

from backend.rag.collection_guard import (
    CollectionMetadataCheckResult,
    CollectionMetadataMismatchError,
    EmbeddingDimensionMismatchError,
    check_collection_metadata,
    check_collection_metadata_from_config,
    load_active_embedding_metadata,
)


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "doc_id": "synthetic_doc",
        "chunk_index": 0,
        "text": "synthetic text that must never be logged",
        "embedding_backend": "gateway_litellm_current",
        "embedding_model": "nomic-embed-text",
        "embedding_dimensions": 768,
        "embedding_contract": "openai_compatible_v1_embeddings",
        "embedding_alias": "quimera_embed",
        "vector": [0.1, 0.2, 0.3],
    }
    payload.update(overrides)
    return payload


def _point(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": "point-a", "payload": payload}


def _client(points: list[dict[str, Any]]) -> Mock:
    client = Mock()
    client.scroll.return_value = (points, None)
    return client


def _check(
    client: Mock,
    collection_name: str = "collection",
    *,
    sample_size: int = 10,
    strict: bool = False,
) -> CollectionMetadataCheckResult:
    return check_collection_metadata(
        client,
        collection_name,
        active_backend="gateway_litellm_current",
        active_model="nomic-embed-text",
        active_dimensions=768,
        active_contract="openai_compatible_v1_embeddings",
        active_alias="quimera_embed",
        sample_size=sample_size,
        strict=strict,
    )


class CollectionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log_messages: list[str] = []
        self.log_sink_id = logger.add(
            self.log_messages.append,
            level="WARNING",
            format="{message}",
        )

    def tearDown(self) -> None:
        logger.remove(self.log_sink_id)

    def test_empty_collection_no_warning_or_error(self) -> None:
        client = _client([])

        result = _check(client)

        self.assertEqual(result.sample.sampled_count, 0)
        self.assertTrue(result.backend_matches)
        self.assertTrue(result.metadata_complete)
        self.assertEqual(self.log_messages, [])

    def test_matching_metadata_all_match(self) -> None:
        result = _check(
            _client([_point(_payload()), _point(_payload(chunk_index=1))]),
        )

        self.assertEqual(result.sample.sampled_count, 2)
        self.assertTrue(result.backend_matches)
        self.assertTrue(result.model_matches)
        self.assertTrue(result.dimensions_match)
        self.assertTrue(result.contract_matches)
        self.assertTrue(result.alias_matches)
        self.assertTrue(result.metadata_complete)
        self.assertEqual(self.log_messages, [])

    def test_backend_mismatch_warns_without_raising(self) -> None:
        result = _check(
            _client([_point(_payload(embedding_backend="direct_ollama_current"))]),
        )

        self.assertFalse(result.backend_matches)
        self.assertTrue(any("collection_backend_mismatch" in msg for msg in self.log_messages))

    def test_model_mismatch_warns_with_reindex_recommendation(self) -> None:
        result = _check(
            _client([_point(_payload(embedding_model="other-model"))]),
        )

        self.assertFalse(result.model_matches)
        joined_logs = "\n".join(self.log_messages)
        self.assertIn("collection_model_mismatch", joined_logs)
        self.assertIn("recommendation=reindex_required", joined_logs)

    def test_contract_mismatch_warns_without_raising(self) -> None:
        result = _check(
            _client([_point(_payload(embedding_contract="legacy_contract"))]),
        )

        self.assertFalse(result.contract_matches)
        self.assertTrue(any("collection_contract_mismatch" in msg for msg in self.log_messages))

    def test_alias_mismatch_warns_without_raising(self) -> None:
        result = _check(
            _client([_point(_payload(embedding_alias="local_embed"))]),
        )

        self.assertFalse(result.alias_matches)
        self.assertTrue(any("collection_alias_mismatch" in msg for msg in self.log_messages))

    def test_metadata_absent_warns_and_counts_missing_payloads(self) -> None:
        result = _check(
            _client([_point({"doc_id": "legacy", "text": "do not log this"})]),
        )

        self.assertEqual(result.sample.metadata_absent_count, 1)
        self.assertFalse(result.metadata_complete)
        self.assertTrue(any("collection_metadata_absent" in msg for msg in self.log_messages))

    def test_dimensions_mismatch_always_raises(self) -> None:
        with self.assertRaises(EmbeddingDimensionMismatchError):
            _check(
                _client([_point(_payload(embedding_dimensions=1536))]),
            )

        self.assertTrue(any("collection_dimension_mismatch" in msg for msg in self.log_messages))

    def test_strict_true_raises_on_backend_model_contract_and_alias_mismatch(self) -> None:
        mismatched_payload = _payload(
            embedding_backend="direct_ollama_current",
            embedding_model="other-model",
            embedding_contract="legacy_contract",
            embedding_alias="local_embed",
        )

        with self.assertRaises(CollectionMetadataMismatchError):
            _check(
                _client([_point(mismatched_payload)]),
                strict=True,
            )

    def test_scroll_uses_payload_without_vectors_and_respects_sample_size(self) -> None:
        client = _client([_point(_payload())])

        _check(client, sample_size=7)

        client.scroll.assert_called_once_with(
            collection_name="collection",
            limit=7,
            with_payload=True,
            with_vectors=False,
        )

    def test_does_not_log_payload_text_or_vectors(self) -> None:
        _check(
            _client(
                [
                    _point(
                        _payload(
                            embedding_backend="direct_ollama_current",
                            text="sensitive synthetic payload text",
                            vector=[9.9, 8.8, 7.7],
                        )
                    )
                ]
            ),
        )

        joined_logs = "\n".join(self.log_messages)
        self.assertNotIn("sensitive synthetic payload text", joined_logs)
        self.assertNotIn("9.9", joined_logs)
        self.assertNotIn("8.8", joined_logs)
        self.assertNotIn("7.7", joined_logs)

    def test_load_active_embedding_metadata_from_config(self) -> None:
        config = """
rag:
  embedding:
    embedding_backend: "gateway_litellm_current"
    embedding_model: "nomic-embed-text"
    embedding_dimensions: 768
    embedding_contract: "openai_compatible_v1_embeddings"
    embedding_alias: "quimera_embed"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "rag_config.yaml"
            config_path.write_text(config, encoding="utf-8")

            active = load_active_embedding_metadata(config_path)

        self.assertEqual(active.backend, "gateway_litellm_current")
        self.assertEqual(active.model, "nomic-embed-text")
        self.assertEqual(active.dimensions, 768)
        self.assertEqual(active.contract, "openai_compatible_v1_embeddings")
        self.assertEqual(active.alias, "quimera_embed")

    def test_check_from_config_uses_loaded_active_values(self) -> None:
        config = """
rag:
  embedding:
    embedding_backend: "gateway_litellm_current"
    embedding_model: "nomic-embed-text"
    embedding_dimensions: 768
    embedding_contract: "openai_compatible_v1_embeddings"
    embedding_alias: "quimera_embed"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "rag_config.yaml"
            config_path.write_text(config, encoding="utf-8")

            result = check_collection_metadata_from_config(
                _client([_point(_payload())]),
                "collection",
                config_path=config_path,
            )

        self.assertTrue(result.backend_matches)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
