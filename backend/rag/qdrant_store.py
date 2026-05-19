"""Qdrant vector store for the local OPENCLAW RAG pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, TypedDict, cast
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models

from backend.rag.sparse_vector import SparseVector


DEFAULT_QDRANT_HOST = "localhost"
DEFAULT_QDRANT_PORT = 6333
DEFAULT_COLLECTION_NAME = "openclaw_knowledge"
DEFAULT_VECTOR_SIZE = 768
DEFAULT_DISTANCE = models.Distance.COSINE
DEFAULT_SECURITY_LEVEL = "Level 2"
RESERVED_PAYLOAD_KEYS = {
    "doc_id",
    "chunk_index",
    "text",
    "ingested_at",
    "security_level",
}

DENSE_VECTOR_NAME: str = "dense"
SPARSE_VECTOR_NAME: str = "sparse"
LEGACY_COLLECTION_NAME: str = "quimera_knowledge"
HYBRID_COLLECTION_NAME: str = "quimera_knowledge_v2"

# Qwen3 0.6B is the efficient local default for the v2 hybrid collection.
# Do not change these values without bumping SCHEMA_VERSION and revalidating
# collection compatibility.
QWEN3_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_PROVIDER: str = "local"
QWEN3_EMBEDDING_DIMENSIONS: int = 1024
QWEN3_EMBEDDING_VERSION: str = "qwen3-embedding-0.6b@pinned"
SCHEMA_VERSION: str = "qdrant-hybrid-v2"

# ⚠️ ATENÇÃO — DOUBLE-IDF TRAP
# fastembed BM25 already applies TF-IDF weights internally.
# Do NOT use modifier=models.Modifier.IDF here. That would apply server-side
# IDF a second time, silently degrading recall without raising an exception.
SPARSE_VECTOR_PARAMS: models.SparseVectorParams = models.SparseVectorParams()


class HybridPointPayload(TypedDict):
    """Required payload metadata for points in the v2 hybrid collection."""

    doc_id: str
    chunk_index: int
    security_level: str
    embedding_model: str
    embedding_provider: str
    embedding_dimensions: int
    embedding_version: str
    schema_version: str


class HybridQdrantClient(Protocol):
    """Synchronous Qdrant client surface used by the hybrid schema helpers."""

    def collection_exists(self, collection_name: str) -> bool: ...

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Mapping[str, models.VectorParams],
        sparse_vectors_config: Mapping[str, models.SparseVectorParams],
    ) -> object: ...

    def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[models.PointStruct],
        wait: bool,
    ) -> object: ...


class AsyncHybridQdrantClient(Protocol):
    """Async Qdrant client surface used by AsyncQdrantHybridStore."""

    async def collection_exists(self, collection_name: str) -> bool: ...

    async def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Mapping[str, models.VectorParams],
        sparse_vectors_config: Mapping[str, models.SparseVectorParams],
    ) -> object: ...

    async def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[models.PointStruct],
        wait: bool,
    ) -> object: ...


@dataclass(frozen=True)
class VectorStoreChunk:
    """Chunk metadata required for vector-store persistence."""

    doc_id: str
    chunk_index: int
    text: str
    security_level: str = DEFAULT_SECURITY_LEVEL
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievedPoint:
    """Search result returned from Qdrant."""

    id: str
    score: float
    doc_id: str
    chunk_index: int
    text: str
    security_level: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict for callers that do not need dataclass semantics."""

        return {
            "id": self.id,
            "score": self.score,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "security_level": self.security_level,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class HybridCollectionConfig:
    """Qdrant v2 hybrid collection contract.

    The collection uses named vectors: ``dense`` for Qwen3 dense embeddings and
    ``sparse`` for BM25/FastEmbed sparse vectors. Future named-vector queries
    with Qdrant's ``using=`` parameter require Qdrant server >= 1.10.
    """

    collection_name: str = HYBRID_COLLECTION_NAME
    dense_dimensions: int = QWEN3_EMBEDDING_DIMENSIONS
    dense_distance: models.Distance = models.Distance.COSINE
    dense_vector_name: str = DENSE_VECTOR_NAME
    sparse_vector_name: str = SPARSE_VECTOR_NAME
    embedding_model: str = QWEN3_EMBEDDING_MODEL
    embedding_provider: str = QWEN3_EMBEDDING_PROVIDER
    embedding_dimensions: int = QWEN3_EMBEDDING_DIMENSIONS
    embedding_version: str = QWEN3_EMBEDDING_VERSION
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if "\x00" in self.collection_name:
            raise ValueError("collection_name cannot contain null bytes")
        if not self.collection_name.strip():
            raise ValueError("collection_name cannot be empty")
        if self.collection_name == LEGACY_COLLECTION_NAME:
            raise ValueError("legacy collection cannot be used for hybrid schema")
        if self.dense_dimensions <= 0:
            raise ValueError("dense_dimensions must be positive integer")
        if self.embedding_dimensions != self.dense_dimensions:
            raise ValueError("embedding_dimensions must match dense_dimensions")
        if self.dense_vector_name == self.sparse_vector_name:
            raise ValueError("dense_vector_name and sparse_vector_name must differ")

    def to_qdrant_vectors_config(self) -> dict[str, object]:
        """Return kwargs ready for ``QdrantClient.create_collection``.

        ⚠️ SPARSE: ``modifier=None`` is intentional. FastEmbed BM25 already
        applies TF-IDF. Adding ``Modifier.IDF`` would cause silent double-IDF.
        """

        return {
            "vectors_config": {
                self.dense_vector_name: models.VectorParams(
                    size=self.dense_dimensions,
                    distance=self.dense_distance,
                )
            },
            "sparse_vectors_config": {
                self.sparse_vector_name: SPARSE_VECTOR_PARAMS,
            },
        }

    def schema_fingerprint(self) -> str:
        """Return a stable SHA-256[:16] fingerprint for the schema contract."""

        payload = {
            "collection_name": self.collection_name,
            "dense_dimensions": self.dense_dimensions,
            "dense_distance": self.dense_distance.value,
            "dense_vector_name": self.dense_vector_name,
            "embedding_model": self.embedding_model,
            "schema_version": self.schema_version,
            "sparse_vector_name": self.sparse_vector_name,
        }
        canonical = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()[:16]


@dataclass
class QdrantVectorStore:
    """Small synchronous wrapper around Qdrant collection operations."""

    collection_name: str = DEFAULT_COLLECTION_NAME
    vector_size: int = DEFAULT_VECTOR_SIZE
    host: str = DEFAULT_QDRANT_HOST
    port: int = DEFAULT_QDRANT_PORT
    distance: models.Distance = DEFAULT_DISTANCE
    client: QdrantClient | None = None
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if not self.collection_name.strip():
            raise ValueError("collection_name cannot be empty")
        if self.vector_size <= 0:
            raise ValueError("vector_size must be greater than zero")
        if self.port <= 0:
            raise ValueError("port must be greater than zero")

        if self.client is None:
            self.client = QdrantClient(host=self.host, port=self.port)
            self._owns_client = True

    def close(self) -> None:
        """Close the owned Qdrant client."""

        if self._owns_client and self.client is not None:
            self.client.close()

    def ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""

        client = self._client()
        if client.collection_exists(self.collection_name):
            return

        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.vector_size,
                distance=self.distance,
            ),
        )

    def upsert(
        self,
        chunks: Sequence[VectorStoreChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Upsert chunk vectors and metadata into Qdrant."""

        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        if not chunks:
            return

        points = [
            models.PointStruct(
                id=_point_id(chunk),
                vector=_validate_vector(vector, self.vector_size),
                payload=_payload_for_chunk(chunk),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        self._client().upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def delete_document(self, document_id: str) -> int:
        """Delete all points for one document id and return count before delete."""

        clean_document_id = _validate_non_empty(document_id, "document_id")
        query_filter = _filter_from_mapping({"doc_id": clean_document_id})
        if query_filter is None:
            raise RuntimeError("document delete filter could not be built")

        existing = self._client().count(
            collection_name=self.collection_name,
            count_filter=query_filter,
            exact=True,
        ).count

        self._client().delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )
        return int(existing)

    def search(
        self,
        vector: Sequence[float],
        top_k: int = 5,
        score_threshold: float | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar chunks and return plain dictionaries."""

        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")

        query_filter = _filter_from_mapping(filters or {})
        results = self._client().query_points(
            collection_name=self.collection_name,
            query=_validate_vector(vector, self.vector_size),
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [_point_to_result(point).as_dict() for point in results.points]

    def count(self) -> int:
        """Return the exact number of points in the collection."""

        return int(
            self._client().count(
                collection_name=self.collection_name,
                exact=True,
            ).count
        )

    def _client(self) -> QdrantClient:
        if self.client is None:
            raise RuntimeError("Qdrant client is not initialized")
        return self.client


@dataclass
class AsyncQdrantHybridStore:
    """Async store for the Qdrant v2 hybrid schema.

    This store only ensures schema and upserts named dense/sparse vectors. It
    does not implement HybridRetriever, fusion, query planning or Agentic RAG.
    Future calls that query named vectors with ``using=`` require Qdrant server
    >= 1.10.
    """

    config: HybridCollectionConfig = field(default_factory=HybridCollectionConfig)
    host: str = DEFAULT_QDRANT_HOST
    port: int = DEFAULT_QDRANT_PORT
    client: AsyncHybridQdrantClient | None = None
    _ensure_lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    _owns_client: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.port <= 0:
            raise ValueError("port must be greater than zero")
        if self.client is None:
            self.client = cast(
                AsyncHybridQdrantClient,
                AsyncQdrantClient(host=self.host, port=self.port),
            )
            self._owns_client = True

    async def close(self) -> None:
        """Close the owned async Qdrant client."""

        if self._owns_client and self.client is not None:
            await cast(AsyncQdrantClient, self.client).close()

    async def ensure_hybrid_collection(self) -> None:
        """Idempotently create the v2 collection, serialized by a process lock."""

        async with self._ensure_lock:
            client = self._client()
            if await client.collection_exists(self.config.collection_name):
                return
            config_kwargs = self.config.to_qdrant_vectors_config()
            await client.create_collection(
                collection_name=self.config.collection_name,
                vectors_config=cast(
                    Mapping[str, models.VectorParams],
                    config_kwargs["vectors_config"],
                ),
                sparse_vectors_config=cast(
                    Mapping[str, models.SparseVectorParams],
                    config_kwargs["sparse_vectors_config"],
                ),
            )

    async def upsert_hybrid_point(
        self,
        *,
        point_id: int | str,
        dense_vector: Sequence[float],
        sparse_vector: SparseVector,
        payload: Mapping[str, object],
    ) -> None:
        """Upsert one point with named dense and sparse vectors."""

        point = build_hybrid_point(
            point_id=point_id,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            payload=payload,
            config=self.config,
        )
        await self._client().upsert(
            collection_name=self.config.collection_name,
            points=[point],
            wait=True,
        )

    def _client(self) -> AsyncHybridQdrantClient:
        if self.client is None:
            raise RuntimeError("Qdrant client is not initialized")
        return self.client


def create_hybrid_collection(
    client: HybridQdrantClient,
    config: HybridCollectionConfig | None = None,
) -> None:
    """Create the v2 hybrid collection schema without touching legacy storage."""

    resolved_config = config or HybridCollectionConfig()
    config_kwargs = resolved_config.to_qdrant_vectors_config()
    client.create_collection(
        collection_name=resolved_config.collection_name,
        vectors_config=cast(
            Mapping[str, models.VectorParams],
            config_kwargs["vectors_config"],
        ),
        sparse_vectors_config=cast(
            Mapping[str, models.SparseVectorParams],
            config_kwargs["sparse_vectors_config"],
        ),
    )


def ensure_hybrid_collection(
    client: HybridQdrantClient,
    config: HybridCollectionConfig | None = None,
) -> None:
    """Create the v2 hybrid collection if missing; validate by name only here."""

    resolved_config = config or HybridCollectionConfig()
    if client.collection_exists(resolved_config.collection_name):
        return
    create_hybrid_collection(client, resolved_config)


def validate_hybrid_payload(
    payload: Mapping[str, object],
    config: HybridCollectionConfig | None = None,
) -> HybridPointPayload:
    """Validate mandatory embedding metadata for ``quimera_knowledge_v2``."""

    resolved_config = config or HybridCollectionConfig()
    doc_id = _validate_payload_text(payload, "doc_id")
    security_level = _validate_payload_text(payload, "security_level")
    embedding_model = _validate_payload_text(payload, "embedding_model")
    embedding_provider = _validate_payload_text(payload, "embedding_provider")
    embedding_version = _validate_payload_text(payload, "embedding_version")
    schema_version = _validate_payload_text(payload, "schema_version")
    chunk_index = _validate_payload_int(payload, "chunk_index")
    embedding_dimensions = _validate_payload_int(payload, "embedding_dimensions")

    if chunk_index < 0:
        raise ValueError("chunk_index cannot be negative")
    if embedding_model != resolved_config.embedding_model:
        raise ValueError(
            "hybrid payload embedding_model does not match Qwen3 v2 contract"
        )
    if embedding_provider != resolved_config.embedding_provider:
        raise ValueError("hybrid payload embedding_provider does not match v2 contract")
    if embedding_dimensions != resolved_config.embedding_dimensions:
        raise ValueError(
            "hybrid payload embedding_dimensions does not match Qwen3 v2 contract"
        )
    if embedding_version != resolved_config.embedding_version:
        raise ValueError("hybrid payload embedding_version does not match v2 contract")
    if schema_version != resolved_config.schema_version:
        raise ValueError("hybrid payload schema_version does not match v2 contract")

    return {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "security_level": security_level,
        "embedding_model": embedding_model,
        "embedding_provider": embedding_provider,
        "embedding_dimensions": embedding_dimensions,
        "embedding_version": embedding_version,
        "schema_version": schema_version,
    }


def build_hybrid_point(
    *,
    point_id: int | str,
    dense_vector: Sequence[float],
    sparse_vector: SparseVector,
    payload: Mapping[str, object],
    config: HybridCollectionConfig | None = None,
) -> models.PointStruct:
    """Build a Qdrant point with named dense and sparse vectors."""

    resolved_config = config or HybridCollectionConfig()
    clean_payload = validate_hybrid_payload(payload, resolved_config)
    dense = _validate_vector(dense_vector, resolved_config.dense_dimensions)
    sparse = models.SparseVector(
        indices=list(sparse_vector.indices),
        values=list(sparse_vector.values),
    )
    return models.PointStruct(
        id=point_id,
        vector={
            resolved_config.dense_vector_name: dense,
            resolved_config.sparse_vector_name: sparse,
        },
        payload=dict(clean_payload),
    )


def upsert_hybrid_point(
    client: HybridQdrantClient,
    *,
    point_id: int | str,
    dense_vector: Sequence[float],
    sparse_vector: SparseVector,
    payload: Mapping[str, object],
    config: HybridCollectionConfig | None = None,
) -> None:
    """Upsert one point into the v2 collection with named dense/sparse vectors."""

    resolved_config = config or HybridCollectionConfig()
    point = build_hybrid_point(
        point_id=point_id,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        payload=payload,
        config=resolved_config,
    )
    client.upsert(
        collection_name=resolved_config.collection_name,
        points=[point],
        wait=True,
    )


def _payload_for_chunk(chunk: VectorStoreChunk) -> dict[str, Any]:
    doc_id = _validate_non_empty(chunk.doc_id, "doc_id")
    text = _validate_non_empty(chunk.text, "text")
    security_level = _validate_non_empty(chunk.security_level, "security_level")

    if chunk.chunk_index < 0:
        raise ValueError("chunk_index cannot be negative")

    metadata = dict(chunk.metadata)
    reserved_keys = RESERVED_PAYLOAD_KEYS.intersection(metadata)
    if reserved_keys:
        keys = ", ".join(sorted(reserved_keys))
        raise ValueError(f"metadata cannot override reserved payload keys: {keys}")

    payload: dict[str, Any] = {
        "doc_id": doc_id,
        "chunk_index": chunk.chunk_index,
        "text": text,
        "ingested_at": datetime.now(UTC).isoformat(),
        "security_level": security_level,
    }
    payload.update(metadata)
    return payload


def _point_id(chunk: VectorStoreChunk) -> str:
    return str(uuid5(NAMESPACE_URL, f"{chunk.doc_id}:{chunk.chunk_index}"))


def _validate_vector(vector: Sequence[float], vector_size: int) -> list[float]:
    if len(vector) != vector_size:
        raise ValueError(f"expected vector size {vector_size}, got {len(vector)}")

    values: list[float] = []
    for value in vector:
        if not isinstance(value, (int, float)):
            raise TypeError("vector values must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError("vector values must be finite")
        values.append(float(value))
    return values


def _validate_non_empty(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{field_name} cannot be empty")
    if "\x00" in clean_value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    return clean_value


def _validate_payload_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} is required and must be a string")
    return _validate_non_empty(value, field_name)


def _validate_payload_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"{field_name} is required and must be an integer")
    return value


def _filter_from_mapping(filters: Mapping[str, Any]) -> models.Filter | None:
    if not filters:
        return None

    return models.Filter(
        must=[
            models.FieldCondition(
                key=key,
                match=models.MatchValue(value=value),
            )
            for key, value in filters.items()
        ]
    )


def _point_to_result(point: models.ScoredPoint) -> RetrievedPoint:
    payload = dict(point.payload or {})
    return RetrievedPoint(
        id=str(point.id),
        score=float(point.score),
        doc_id=str(payload.get("doc_id", "")),
        chunk_index=int(payload.get("chunk_index", -1)),
        text=str(payload.get("text", "")),
        security_level=str(payload.get("security_level", "")),
        payload=payload,
    )


__all__ = [
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "LEGACY_COLLECTION_NAME",
    "HYBRID_COLLECTION_NAME",
    "QWEN3_EMBEDDING_MODEL",
    "QWEN3_EMBEDDING_PROVIDER",
    "QWEN3_EMBEDDING_DIMENSIONS",
    "QWEN3_EMBEDDING_VERSION",
    "SCHEMA_VERSION",
    "SPARSE_VECTOR_PARAMS",
    "DEFAULT_COLLECTION_NAME",
    "VectorStoreChunk",
    "RetrievedPoint",
    "QdrantVectorStore",
    "HybridCollectionConfig",
    "HybridPointPayload",
    "validate_hybrid_payload",
    "build_hybrid_point",
    "ensure_hybrid_collection",
    "create_hybrid_collection",
    "upsert_hybrid_point",
    "AsyncQdrantHybridStore",
]
