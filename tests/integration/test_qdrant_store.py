from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from backend.rag.qdrant_store import QdrantVectorStore, VectorStoreChunk


VECTOR_SIZE = 4


@pytest.fixture
def temp_collection() -> str:
    return f"openclaw_test_{uuid4().hex}"


@pytest.fixture
def qdrant_client() -> QdrantClient:
    return QdrantClient(":memory:")


@pytest.fixture
def store(
    qdrant_client: QdrantClient,
    temp_collection: str,
) -> Iterator[QdrantVectorStore]:
    vector_store = QdrantVectorStore(
        collection_name=temp_collection,
        vector_size=VECTOR_SIZE,
        client=qdrant_client,
    )
    try:
        yield vector_store
    finally:
        if qdrant_client.collection_exists(temp_collection):
            qdrant_client.delete_collection(temp_collection)
        qdrant_client.close()


def _chunk(doc_id: str, index: int, text: str) -> VectorStoreChunk:
    return VectorStoreChunk(
        doc_id=doc_id,
        chunk_index=index,
        text=text,
        security_level="Level 2",
        metadata={"source": "synthetic"},
    )


@pytest.mark.integration
def test_ensure_collection_is_idempotent(store: QdrantVectorStore) -> None:
    store.ensure_collection()
    store.ensure_collection()

    assert store.count() == 0


@pytest.mark.integration
def test_upsert_and_count(store: QdrantVectorStore) -> None:
    store.ensure_collection()
    store.upsert(
        [_chunk("doc-a", 0, "conteudo sintetico A")],
        [[1.0, 0.0, 0.0, 0.0]],
    )

    assert store.count() == 1


@pytest.mark.integration
def test_search_returns_payload_and_score_threshold(store: QdrantVectorStore) -> None:
    store.ensure_collection()
    store.upsert(
        [
            _chunk("doc-a", 0, "Selic sintetica"),
            _chunk("doc-b", 0, "Inflacao sintetica"),
        ],
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ],
    )

    results = store.search([1.0, 0.0, 0.0, 0.0], top_k=1, score_threshold=0.5)

    assert len(results) == 1
    assert results[0]["doc_id"] == "doc-a"
    assert results[0]["chunk_index"] == 0
    assert results[0]["text"] == "Selic sintetica"
    assert results[0]["payload"]["source"] == "synthetic"
    assert results[0]["score"] >= 0.5


@pytest.mark.integration
def test_search_filters_by_payload(store: QdrantVectorStore) -> None:
    store.ensure_collection()
    store.upsert(
        [
            _chunk("doc-a", 0, "chunk A"),
            _chunk("doc-b", 0, "chunk B"),
        ],
        [
            [1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
        ],
    )

    results = store.search(
        [1.0, 0.0, 0.0, 0.0],
        top_k=5,
        filters={"doc_id": "doc-b"},
    )

    assert [result["doc_id"] for result in results] == ["doc-b"]


@pytest.mark.integration
def test_delete_document_removes_only_matching_document(
    store: QdrantVectorStore,
) -> None:
    store.ensure_collection()
    store.upsert(
        [
            _chunk("doc-a", 0, "chunk A0"),
            _chunk("doc-a", 1, "chunk A1"),
            _chunk("doc-b", 0, "chunk B0"),
        ],
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.9, 0.1, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ],
    )

    deleted = store.delete_document("doc-a")

    assert deleted == 2
    assert store.count() == 1
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=5)
    assert [result["doc_id"] for result in results] == ["doc-b"]


@pytest.mark.integration
def test_validation_errors(store: QdrantVectorStore) -> None:
    store.ensure_collection()

    with pytest.raises(ValueError):
        store.upsert([_chunk("doc-a", 0, "chunk")], [[1.0, 0.0]])
    with pytest.raises(ValueError):
        store.upsert([_chunk("doc-a", 0, "chunk")], [])
    with pytest.raises(ValueError):
        store.upsert(
            [
                VectorStoreChunk(
                    doc_id="doc-a",
                    chunk_index=0,
                    text="chunk",
                    metadata={"doc_id": "override"},
                )
            ],
            [[1.0, 0.0, 0.0, 0.0]],
        )
    with pytest.raises(ValueError):
        store.search([1.0, 0.0, 0.0, 0.0], top_k=0)
    with pytest.raises(ValueError):
        store.delete_document(" ")
