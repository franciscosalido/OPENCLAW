"""Unit tests for the Qdrant hybrid v2 collection contract."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Mapping, Sequence
from typing import Any, cast

from qdrant_client.http import models

from backend.rag.qdrant_store import (
    DENSE_VECTOR_NAME,
    HYBRID_COLLECTION_NAME,
    LEGACY_COLLECTION_NAME,
    QWEN3_EMBEDDING_DIMENSIONS,
    QWEN3_EMBEDDING_MODEL,
    QWEN3_EMBEDDING_PROVIDER,
    QWEN3_EMBEDDING_VERSION,
    SCHEMA_VERSION,
    SPARSE_VECTOR_NAME,
    SPARSE_VECTOR_PARAMS,
    AsyncQdrantHybridStore,
    HybridCollectionConfig,
    HybridPointPayload,
    QdrantVectorStore,
    build_hybrid_point,
    create_hybrid_collection,
    ensure_hybrid_collection,
    upsert_hybrid_point,
    validate_hybrid_payload,
)
from backend.rag.sparse_vector import SparseVector


def _valid_payload(**overrides: object) -> HybridPointPayload:
    payload: dict[str, object] = {
        "doc_id": "doc-001",
        "chunk_index": 0,
        "security_level": "Level 0",
        "embedding_model": QWEN3_EMBEDDING_MODEL,
        "embedding_provider": QWEN3_EMBEDDING_PROVIDER,
        "embedding_dimensions": QWEN3_EMBEDDING_DIMENSIONS,
        "embedding_version": QWEN3_EMBEDDING_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    payload.update(overrides)
    return cast(HybridPointPayload, payload)


class FakeSyncQdrantClient:
    def __init__(self, *, exists: bool = False) -> None:
        self.exists = exists
        self.created: list[dict[str, object]] = []
        self.upserts: list[dict[str, object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.exists and collection_name == HYBRID_COLLECTION_NAME

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Mapping[str, models.VectorParams],
        sparse_vectors_config: Mapping[str, models.SparseVectorParams],
    ) -> object:
        self.created.append(
            {
                "collection_name": collection_name,
                "vectors_config": dict(vectors_config),
                "sparse_vectors_config": dict(sparse_vectors_config),
            }
        )
        self.exists = True
        return True

    def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[models.PointStruct],
        wait: bool,
    ) -> object:
        self.upserts.append(
            {
                "collection_name": collection_name,
                "points": list(points),
                "wait": wait,
            }
        )
        return True


class FakeAsyncQdrantClient:
    def __init__(self) -> None:
        self.exists = False
        self.created: list[dict[str, object]] = []
        self.upserts: list[dict[str, object]] = []
        self.exists_calls = 0

    async def collection_exists(self, collection_name: str) -> bool:
        self.exists_calls += 1
        await asyncio.sleep(0)
        return self.exists and collection_name == HYBRID_COLLECTION_NAME

    async def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Mapping[str, models.VectorParams],
        sparse_vectors_config: Mapping[str, models.SparseVectorParams],
    ) -> object:
        await asyncio.sleep(0)
        self.created.append(
            {
                "collection_name": collection_name,
                "vectors_config": dict(vectors_config),
                "sparse_vectors_config": dict(sparse_vectors_config),
            }
        )
        self.exists = True
        return True

    async def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[models.PointStruct],
        wait: bool,
    ) -> object:
        self.upserts.append(
            {
                "collection_name": collection_name,
                "points": list(points),
                "wait": wait,
            }
        )
        return True


class HybridCollectionConfigTests(unittest.TestCase):
    def test_default_contract_uses_qwen3_dense_and_bm25_sparse_names(self) -> None:
        config = HybridCollectionConfig()

        self.assertEqual(config.collection_name, HYBRID_COLLECTION_NAME)
        self.assertEqual(config.dense_vector_name, DENSE_VECTOR_NAME)
        self.assertEqual(config.sparse_vector_name, SPARSE_VECTOR_NAME)
        self.assertEqual(config.embedding_model, QWEN3_EMBEDDING_MODEL)
        self.assertEqual(config.embedding_dimensions, 1024)

    def test_qdrant_schema_uses_named_dense_and_sparse_vectors(self) -> None:
        config = HybridCollectionConfig()
        schema = config.to_qdrant_vectors_config()
        vectors = cast(dict[str, models.VectorParams], schema["vectors_config"])
        sparse = cast(
            dict[str, models.SparseVectorParams], schema["sparse_vectors_config"]
        )

        self.assertEqual(set(vectors), {"dense"})
        self.assertEqual(vectors["dense"].size, 1024)
        self.assertEqual(vectors["dense"].distance, models.Distance.COSINE)
        self.assertEqual(set(sparse), {"sparse"})
        self.assertIs(sparse["sparse"], SPARSE_VECTOR_PARAMS)

    def test_sparse_vector_params_never_use_idf_modifier(self) -> None:
        self.assertIsNone(SPARSE_VECTOR_PARAMS.modifier)

    def test_config_rejects_legacy_collection_and_bad_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy collection"):
            HybridCollectionConfig(collection_name=LEGACY_COLLECTION_NAME)
        with self.assertRaisesRegex(ValueError, "null bytes"):
            HybridCollectionConfig(collection_name="bad\x00name")
        with self.assertRaisesRegex(ValueError, "must differ"):
            HybridCollectionConfig(dense_vector_name="same", sparse_vector_name="same")

    def test_config_rejects_dimension_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedding_dimensions"):
            HybridCollectionConfig(dense_dimensions=1024, embedding_dimensions=4096)

    def test_schema_fingerprint_is_stable_and_material(self) -> None:
        first = HybridCollectionConfig()
        second = HybridCollectionConfig()
        changed = HybridCollectionConfig(collection_name="quimera_knowledge_v3")

        self.assertEqual(first.schema_fingerprint(), second.schema_fingerprint())
        self.assertNotEqual(first.schema_fingerprint(), changed.schema_fingerprint())


class HybridCollectionOperationTests(unittest.TestCase):
    def test_create_hybrid_collection_calls_qdrant_with_v2_schema(self) -> None:
        client = FakeSyncQdrantClient()

        create_hybrid_collection(client)

        self.assertEqual(len(client.created), 1)
        created = client.created[0]
        self.assertEqual(created["collection_name"], HYBRID_COLLECTION_NAME)
        vectors = cast(dict[str, models.VectorParams], created["vectors_config"])
        sparse = cast(
            dict[str, models.SparseVectorParams], created["sparse_vectors_config"]
        )
        self.assertEqual(vectors["dense"].size, QWEN3_EMBEDDING_DIMENSIONS)
        self.assertIsNone(sparse["sparse"].modifier)

    def test_ensure_hybrid_collection_is_idempotent(self) -> None:
        client = FakeSyncQdrantClient(exists=True)

        ensure_hybrid_collection(client)

        self.assertEqual(client.created, [])

    def test_legacy_qdrant_vector_store_default_remains_unchanged(self) -> None:
        store = QdrantVectorStore(client=cast(Any, FakeSyncQdrantClient()))

        self.assertEqual(store.collection_name, "openclaw_knowledge")
        self.assertEqual(store.vector_size, 768)


class HybridPayloadValidationTests(unittest.TestCase):
    def test_valid_payload_is_returned_as_typed_payload(self) -> None:
        payload = validate_hybrid_payload(_valid_payload())

        self.assertEqual(payload["embedding_model"], QWEN3_EMBEDDING_MODEL)
        self.assertEqual(payload["embedding_dimensions"], 1024)

    def test_payload_rejects_nomic_or_wrong_dimensions(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedding_model"):
            validate_hybrid_payload(_valid_payload(embedding_model="nomic-embed-text"))
        with self.assertRaisesRegex(ValueError, "embedding_dimensions"):
            validate_hybrid_payload(_valid_payload(embedding_dimensions=768))

    def test_payload_rejects_wrong_provider_version_or_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedding_provider"):
            validate_hybrid_payload(_valid_payload(embedding_provider="ollama"))
        with self.assertRaisesRegex(ValueError, "embedding_version"):
            validate_hybrid_payload(_valid_payload(embedding_version="v0"))
        with self.assertRaisesRegex(ValueError, "schema_version"):
            validate_hybrid_payload(_valid_payload(schema_version="old-schema"))

    def test_payload_rejects_missing_empty_or_null_byte_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "doc_id"):
            validate_hybrid_payload(_valid_payload(doc_id=" "))
        with self.assertRaisesRegex(ValueError, "security_level"):
            validate_hybrid_payload(_valid_payload(security_level="Level\x000"))
        with self.assertRaisesRegex(ValueError, "chunk_index"):
            validate_hybrid_payload(_valid_payload(chunk_index=-1))


class HybridPointTests(unittest.TestCase):
    def test_build_hybrid_point_uses_named_dense_and_sparse_vectors(self) -> None:
        point = build_hybrid_point(
            point_id="point-1",
            dense_vector=[0.1] * QWEN3_EMBEDDING_DIMENSIONS,
            sparse_vector=SparseVector(indices=[7, 3], values=[0.4, 0.2]),
            payload=_valid_payload(),
        )

        vector = cast(dict[str, object], point.vector)
        self.assertEqual(set(vector), {"dense", "sparse"})
        self.assertEqual(cast(list[float], vector["dense"])[0], 0.1)
        sparse = cast(models.SparseVector, vector["sparse"])
        self.assertEqual(sparse.indices, [7, 3])
        self.assertEqual(sparse.values, [0.4, 0.2])
        payload = cast(dict[str, object], point.payload)
        self.assertEqual(payload["embedding_model"], QWEN3_EMBEDDING_MODEL)

    def test_build_hybrid_point_rejects_wrong_dense_dimension(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "dense_vector has 1d, spec expects 1024d"
        ):
            build_hybrid_point(
                point_id="point-1",
                dense_vector=[0.1],
                sparse_vector=SparseVector(indices=[1], values=[1.0]),
                payload=_valid_payload(),
            )

    def test_upsert_hybrid_point_writes_only_to_v2_collection(self) -> None:
        client = FakeSyncQdrantClient()

        upsert_hybrid_point(
            client,
            point_id=1,
            dense_vector=[0.0] * QWEN3_EMBEDDING_DIMENSIONS,
            sparse_vector=SparseVector(indices=[1], values=[1.0]),
            payload=_valid_payload(),
        )

        self.assertEqual(len(client.upserts), 1)
        self.assertEqual(client.upserts[0]["collection_name"], HYBRID_COLLECTION_NAME)
        self.assertTrue(client.upserts[0]["wait"])

    def test_upsert_hybrid_point_rejects_wrong_dense_dimension_before_client_call(
        self,
    ) -> None:
        client = FakeSyncQdrantClient()

        with self.assertRaisesRegex(
            ValueError,
            "dense_vector has 768d, spec expects 1024d",
        ):
            upsert_hybrid_point(
                client,
                point_id=1,
                dense_vector=[0.0] * 768,
                sparse_vector=SparseVector(indices=[1], values=[1.0]),
                payload=_valid_payload(),
            )

        self.assertEqual(client.upserts, [])


class AsyncQdrantHybridStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_ensure_uses_single_create_call(self) -> None:
        client = FakeAsyncQdrantClient()
        store = AsyncQdrantHybridStore(client=client)

        await asyncio.gather(*(store.ensure_hybrid_collection() for _ in range(5)))

        self.assertEqual(len(client.created), 1)
        self.assertGreaterEqual(client.exists_calls, 5)

    async def test_async_upsert_uses_named_v2_collection(self) -> None:
        client = FakeAsyncQdrantClient()
        store = AsyncQdrantHybridStore(client=client)

        await store.upsert_hybrid_point(
            point_id="point-1",
            dense_vector=[0.0] * QWEN3_EMBEDDING_DIMENSIONS,
            sparse_vector=SparseVector(indices=[1], values=[1.0]),
            payload=_valid_payload(),
        )

        self.assertEqual(len(client.upserts), 1)
        self.assertEqual(client.upserts[0]["collection_name"], HYBRID_COLLECTION_NAME)

    async def test_async_upsert_rejects_wrong_dense_dimension_before_client_call(
        self,
    ) -> None:
        client = FakeAsyncQdrantClient()
        store = AsyncQdrantHybridStore(client=client)

        with self.assertRaisesRegex(
            ValueError,
            "dense_vector has 768d, spec expects 1024d",
        ):
            await store.upsert_hybrid_point(
                point_id="point-1",
                dense_vector=[0.0] * 768,
                sparse_vector=SparseVector(indices=[1], values=[1.0]),
                payload=_valid_payload(),
            )

        self.assertEqual(client.upserts, [])


if __name__ == "__main__":
    unittest.main()
