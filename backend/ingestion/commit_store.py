"""Commit store for controlled dual-corpus ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.rag.collection_guard import (
    ActiveEmbeddingMetadata,
    assert_collection_namespace,
    load_active_embedding_metadata,
)
from backend.rag.embedder_factory import RagEmbedder, create_rag_embedder
from backend.rag.qdrant_store import QdrantVectorStore, VectorStoreChunk


DUAL_CORPUS_COLLECTIONS: Mapping[str, str] = {
    "internal": "openclaw_internal",
    "financial": "openclaw_financial",
}


class SyncVectorStore(Protocol):
    """Synchronous vector store subset used by bootstrap commits."""

    collection_name: str

    def ensure_collection(self) -> None:
        """Create the collection if needed."""

    def upsert(
        self,
        chunks: Sequence[VectorStoreChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Upsert vectorized chunks."""


@dataclass
class QdrantIngestionCommitStore:
    """Commit controlled chunks into one mapped Qdrant collection."""

    collection_name: str
    corpus: str
    vector_store: SyncVectorStore | None = None
    embedder: RagEmbedder | None = None
    embedding_metadata: ActiveEmbeddingMetadata | None = None

    def __post_init__(self) -> None:
        self.collection_name = assert_collection_namespace(
            self.collection_name,
            DUAL_CORPUS_COLLECTIONS,
        )
        expected_collection = DUAL_CORPUS_COLLECTIONS.get(self.corpus)
        if expected_collection != self.collection_name:
            raise ValueError("corpus does not match mapped collection namespace")
        if self.vector_store is None:
            self.vector_store = QdrantVectorStore(collection_name=self.collection_name)
        if self.embedding_metadata is None:
            self.embedding_metadata = load_active_embedding_metadata()

    def commit(self, chunks: Sequence[VectorStoreChunk], *, collection: str | None) -> None:
        """Embed and upsert chunks into the closed mapped collection."""

        requested_collection = collection or self.collection_name
        assert_collection_namespace(requested_collection, DUAL_CORPUS_COLLECTIONS)
        if requested_collection != self.collection_name:
            raise ValueError("requested collection does not match commit store namespace")
        if self.vector_store is None:
            raise RuntimeError("vector_store is not initialized")
        if self.embedding_metadata is None:
            raise RuntimeError("embedding_metadata is not initialized")

        safe_chunks = [
            _with_commit_metadata(
                chunk,
                corpus=self.corpus,
                collection_name=self.collection_name,
                embedding_metadata=self.embedding_metadata,
            )
            for chunk in chunks
        ]
        if not safe_chunks:
            return

        self.vector_store.ensure_collection()
        vectors = _embed_chunks(self.embedder, safe_chunks)
        self.vector_store.upsert(safe_chunks, vectors)


def _with_commit_metadata(
    chunk: VectorStoreChunk,
    *,
    corpus: str,
    collection_name: str,
    embedding_metadata: ActiveEmbeddingMetadata,
) -> VectorStoreChunk:
    metadata = dict(chunk.metadata)
    metadata.update(
        {
            "corpus": corpus,
            "namespace": collection_name,
            "collection_name": collection_name,
            "embedding_backend": embedding_metadata.backend,
            "embedding_model": embedding_metadata.model,
            "embedding_dimensions": embedding_metadata.dimensions,
            "embedding_contract": embedding_metadata.contract,
            "embedding_alias": embedding_metadata.alias,
        }
    )
    _validate_chunk_namespace(metadata, corpus=corpus, collection_name=collection_name)
    return VectorStoreChunk(
        doc_id=chunk.doc_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        security_level=chunk.security_level,
        metadata=metadata,
    )


def _validate_chunk_namespace(
    metadata: Mapping[str, object],
    *,
    corpus: str,
    collection_name: str,
) -> None:
    if metadata.get("corpus") != corpus:
        raise ValueError("chunk corpus metadata does not match commit corpus")
    if metadata.get("namespace") != collection_name:
        raise ValueError("chunk namespace metadata does not match collection")
    if corpus == "internal" and collection_name != DUAL_CORPUS_COLLECTIONS["internal"]:
        raise ValueError("internal corpus cannot write outside openclaw_internal")
    if corpus == "financial" and collection_name != DUAL_CORPUS_COLLECTIONS["financial"]:
        raise ValueError("financial corpus cannot write outside openclaw_financial")


def _embed_chunks(
    embedder: RagEmbedder | None,
    chunks: Sequence[VectorStoreChunk],
) -> list[list[float]]:
    active_embedder = embedder or create_rag_embedder()
    # A0-PR02 bootstrap is intentionally synchronous. Replace this bridge before
    # wiring commit into an async runtime such as FastAPI or pytest-asyncio.
    return asyncio.run(active_embedder.embed_batch([chunk.text for chunk in chunks]))
