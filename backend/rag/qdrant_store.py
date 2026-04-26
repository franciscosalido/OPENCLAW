"""Qdrant vector store for the local OPENCLAW RAG pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.http import models


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
        values.append(float(value))
    return values


def _validate_non_empty(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{field_name} cannot be empty")
    return clean_value


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
