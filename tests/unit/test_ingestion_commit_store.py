from __future__ import annotations

import unittest
from collections.abc import Sequence

from backend.ingestion.commit_store import QdrantIngestionCommitStore
from backend.rag.collection_guard import ActiveEmbeddingMetadata
from backend.rag.qdrant_store import VectorStoreChunk


class FakeEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _text in texts]


class FakeVectorStore:
    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        self.ensure_calls = 0
        self.upserts: list[
            tuple[Sequence[VectorStoreChunk], Sequence[Sequence[float]]]
        ] = []

    def ensure_collection(self) -> None:
        self.ensure_calls += 1

    def upsert(
        self,
        chunks: Sequence[VectorStoreChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        self.upserts.append((chunks, vectors))


def _metadata() -> ActiveEmbeddingMetadata:
    return ActiveEmbeddingMetadata(
        backend="gateway_litellm_current",
        model="nomic-embed-text",
        dimensions=3,
        contract="openai_compatible_v1_embeddings",
        alias="quimera_embed",
    )


def _chunk(policy: str = "internal") -> VectorStoreChunk:
    return VectorStoreChunk(
        doc_id="doc_a",
        chunk_index=0,
        text="conteudo sintetico",
        metadata={
            "source_id": "source-a",
            "ingestion_policy": policy,
        },
    )


class IngestionCommitStoreTests(unittest.TestCase):
    def test_arbitrary_collection_rejected(self) -> None:
        with self.assertRaises(ValueError):
            QdrantIngestionCommitStore(
                collection_name="custom_collection",
                corpus="internal",
                vector_store=FakeVectorStore("custom_collection"),
                embedder=FakeEmbedder(),
                embedding_metadata=_metadata(),
            )

    def test_openclaw_knowledge_rejected(self) -> None:
        with self.assertRaises(ValueError):
            QdrantIngestionCommitStore(
                collection_name="openclaw_knowledge",
                corpus="internal",
                vector_store=FakeVectorStore("openclaw_knowledge"),
                embedder=FakeEmbedder(),
                embedding_metadata=_metadata(),
            )

    def test_internal_never_writes_to_financial_collection(self) -> None:
        with self.assertRaises(ValueError):
            QdrantIngestionCommitStore(
                collection_name="openclaw_financial",
                corpus="internal",
                vector_store=FakeVectorStore("openclaw_financial"),
                embedder=FakeEmbedder(),
                embedding_metadata=_metadata(),
            )

    def test_financial_never_writes_to_internal_collection(self) -> None:
        with self.assertRaises(ValueError):
            QdrantIngestionCommitStore(
                collection_name="openclaw_internal",
                corpus="financial",
                vector_store=FakeVectorStore("openclaw_internal"),
                embedder=FakeEmbedder(),
                embedding_metadata=_metadata(),
            )

    def test_commit_enriches_metadata_and_upserts_to_mapped_collection(self) -> None:
        vector_store = FakeVectorStore("openclaw_internal")
        store = QdrantIngestionCommitStore(
            collection_name="openclaw_internal",
            corpus="internal",
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            embedding_metadata=_metadata(),
        )

        store.commit([_chunk()], collection="openclaw_internal")

        self.assertEqual(vector_store.ensure_calls, 1)
        self.assertEqual(len(vector_store.upserts), 1)
        chunks, vectors = vector_store.upserts[0]
        self.assertEqual(vectors, [[1.0, 0.0, 0.0]])
        metadata = chunks[0].metadata
        self.assertEqual(metadata["corpus"], "internal")
        self.assertEqual(metadata["namespace"], "openclaw_internal")
        self.assertEqual(metadata["embedding_alias"], "quimera_embed")
        self.assertEqual(metadata["source_id"], "source-a")

    def test_empty_commit_does_not_mutate_vector_store(self) -> None:
        vector_store = FakeVectorStore("openclaw_financial")
        store = QdrantIngestionCommitStore(
            collection_name="openclaw_financial",
            corpus="financial",
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            embedding_metadata=_metadata(),
        )

        store.commit([], collection="openclaw_financial")

        self.assertEqual(vector_store.ensure_calls, 0)
        self.assertEqual(vector_store.upserts, [])


if __name__ == "__main__":
    unittest.main()
