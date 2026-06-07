"""Qdrant hot-path store for QUIMERA working memory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from backend.observability.decorators import traced_cache
from backend.working_memory.config import WorkingMemoryDistance, WorkingMemorySettings
from backend.working_memory.models import WorkingMemoryPoint, point_from_payload


WORKING_MEMORY_PAYLOAD_INDEXES: Mapping[str, models.PayloadSchemaType] = {
    "agent_id": models.PayloadSchemaType.KEYWORD,
    "session_id": models.PayloadSchemaType.KEYWORD,
    "task_id": models.PayloadSchemaType.KEYWORD,
    "memory_kind": models.PayloadSchemaType.KEYWORD,
    "topic": models.PayloadSchemaType.KEYWORD,
    "expires_at": models.PayloadSchemaType.DATETIME,
    "checkpoint_id": models.PayloadSchemaType.KEYWORD,
    "schema_version": models.PayloadSchemaType.KEYWORD,
    "importance": models.PayloadSchemaType.FLOAT,
}


class WorkingMemoryQdrantClient(Protocol):
    async def collection_exists(self, **kwargs: Any) -> bool: ...
    async def create_collection(self, **kwargs: Any) -> Any: ...
    async def get_collection(self, **kwargs: Any) -> Any: ...
    async def create_payload_index(self, **kwargs: Any) -> Any: ...
    async def upsert(self, **kwargs: Any) -> Any: ...
    async def query_points(self, **kwargs: Any) -> Any: ...
    async def scroll(self, **kwargs: Any) -> tuple[list[Any], Any]: ...
    async def set_payload(self, **kwargs: Any) -> Any: ...
    async def delete(self, **kwargs: Any) -> Any: ...


class WorkingMemoryQdrantStore:
    """Dedicated Qdrant collection for small, restorable working memory."""

    def __init__(
        self,
        client: AsyncQdrantClient | WorkingMemoryQdrantClient,
        settings: WorkingMemorySettings,
    ) -> None:
        self._client = client
        self._settings = settings

    async def ensure_collection(self) -> None:
        if await self._client.collection_exists(collection_name=self._settings.collection_name):
            await self.assert_collection_compatible()
        else:
            await self._client.create_collection(
                collection_name=self._settings.collection_name,
                vectors_config={
                    self._settings.vector_name: models.VectorParams(
                        size=self._settings.vector_size,
                        distance=qdrant_distance(self._settings.distance),
                        on_disk=False,
                    )
                },
                optimizers_config=models.OptimizersConfigDiff(default_segment_number=2),
            )
        for field_name, field_schema in WORKING_MEMORY_PAYLOAD_INDEXES.items():
            await self._client.create_payload_index(
                collection_name=self._settings.collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )

    async def assert_collection_compatible(self) -> None:
        info = await self._client.get_collection(collection_name=self._settings.collection_name)
        vectors = _extract_vectors_config(info)
        if self._settings.vector_name not in vectors:
            raise ValueError("working memory vector name mismatch")
        vector_config = vectors[self._settings.vector_name]
        raw_size = vector_config.get("size")
        if not isinstance(raw_size, int):
            raise ValueError("working memory vector size is invalid")
        if raw_size != self._settings.vector_size:
            raise ValueError("working memory vector size mismatch")
        if _normalize_distance(str(vector_config["distance"])) != self._settings.distance:
            raise ValueError("working memory distance mismatch")
        if vector_config.get("on_disk") is True:
            raise ValueError("working memory vector storage must be in-memory")

    @traced_cache(operation="working_memory.upsert", collection="quimera_working_memory")
    async def upsert_memory_point(self, point: WorkingMemoryPoint) -> str:
        self._validate_vector_dim(point.vector)
        await self._client.upsert(
            collection_name=self._settings.collection_name,
            points=[
                models.PointStruct(
                    id=point.point_id,
                    vector={self._settings.vector_name: list(point.vector)},
                    payload=point.to_qdrant_payload(),
                )
            ],
            wait=True,
        )
        return point.point_id

    @traced_cache(operation="working_memory.query", collection="quimera_working_memory")
    async def query_working_memory(
        self,
        *,
        agent_id: str,
        session_id: str,
        query_vector: Sequence[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        clean_limit = _validate_limit(limit)
        vector = self._validate_vector_dim(tuple(float(item) for item in query_vector))
        result = await self._client.query_points(
            collection_name=self._settings.collection_name,
            query=list(vector),
            using=self._settings.vector_name,
            query_filter=_agent_session_filter(agent_id=agent_id, session_id=session_id),
            limit=clean_limit,
            with_payload=True,
            with_vectors=False,
        )
        points = list(getattr(result, "points", []))
        return [_safe_result_from_point(point) for point in points]

    async def list_session_memory(self, *, agent_id: str, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        points, _ = await self._client.scroll(
            collection_name=self._settings.collection_name,
            scroll_filter=_agent_session_filter(agent_id=agent_id, session_id=session_id),
            limit=_validate_limit(limit),
            with_payload=True,
            with_vectors=False,
        )
        return [_safe_result_from_point(point) for point in points]

    async def mark_checkpointed(self, *, point_ids: Iterable[str], checkpoint_id: str) -> None:
        ids = [point_id for point_id in point_ids if point_id.strip()]
        if not ids:
            return
        await self._client.set_payload(
            collection_name=self._settings.collection_name,
            payload={"checkpoint_id": checkpoint_id},
            points=models.PointIdsList(points=cast(Any, ids)),
            wait=True,
        )

    async def delete_expired_points(self, *, agent_id: str | None = None, session_id: str | None = None) -> int:
        conditions: list[models.Condition] = [
            models.FieldCondition(
                key="expires_at",
                range=models.DatetimeRange(lte=datetime.now(UTC)),
            )
        ]
        if agent_id is not None:
            conditions.append(models.FieldCondition(key="agent_id", match=models.MatchValue(value=agent_id)))
        if session_id is not None:
            conditions.append(models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id)))
        await self._client.delete(
            collection_name=self._settings.collection_name,
            points_selector=models.FilterSelector(filter=models.Filter(must=conditions)),
            wait=True,
        )
        return 0

    async def delete_session_points(self, *, agent_id: str, session_id: str) -> int:
        await self._client.delete(
            collection_name=self._settings.collection_name,
            points_selector=models.FilterSelector(filter=_agent_session_filter(agent_id=agent_id, session_id=session_id)),
            wait=True,
        )
        return 0

    async def export_session_points_for_snapshot(self, *, agent_id: str, session_id: str, limit: int | None = None) -> list[WorkingMemoryPoint]:
        points, _ = await self._client.scroll(
            collection_name=self._settings.collection_name,
            scroll_filter=_agent_session_filter(agent_id=agent_id, session_id=session_id),
            limit=limit or self._settings.max_points_per_session,
            with_payload=True,
            with_vectors=True,
        )
        return [_point_from_qdrant_point(point, vector_name=self._settings.vector_name) for point in points]

    async def restore_points_from_snapshot(self, points: list[WorkingMemoryPoint]) -> int:
        if not points:
            return 0
        for point in points:
            self._validate_vector_dim(point.vector)
        await self._client.upsert(
            collection_name=self._settings.collection_name,
            points=[
                models.PointStruct(
                    id=point.point_id,
                    vector={self._settings.vector_name: list(point.vector)},
                    payload=point.to_qdrant_payload(),
                )
                for point in points
            ],
            wait=True,
        )
        return len(points)

    def _validate_vector_dim(self, vector: Sequence[float]) -> tuple[float, ...]:
        clean = tuple(float(item) for item in vector)
        if len(clean) != self._settings.vector_size:
            raise ValueError("working memory vector dimension mismatch")
        return clean


def qdrant_distance(distance: WorkingMemoryDistance) -> models.Distance:
    if distance == "Cosine":
        return models.Distance.COSINE
    if distance == "Dot":
        return models.Distance.DOT
    if distance == "Euclid":
        return models.Distance.EUCLID
    if distance == "Manhattan":
        return models.Distance.MANHATTAN
    raise ValueError("unsupported working memory distance")


def _agent_session_filter(*, agent_id: str, session_id: str) -> models.Filter:
    UUID(session_id)
    return models.Filter(
        must=[
            models.FieldCondition(key="agent_id", match=models.MatchValue(value=agent_id)),
            models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id)),
        ]
    )


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return limit


def _safe_result_from_point(point: Any) -> dict[str, Any]:
    payload = dict(getattr(point, "payload", {}) or {})
    return {
        "point_id": str(getattr(point, "id", "")),
        "score": float(getattr(point, "score", 0.0)),
        "agent_id": payload.get("agent_id"),
        "session_id": payload.get("session_id"),
        "memory_kind": payload.get("memory_kind"),
        "topic": payload.get("topic"),
        "safe_summary": payload.get("safe_summary"),
        "importance": payload.get("importance"),
        "expires_at": payload.get("expires_at"),
        "payload_checksum": payload.get("payload_checksum"),
    }


def _point_from_qdrant_point(point: Any, *, vector_name: str) -> WorkingMemoryPoint:
    payload = dict(getattr(point, "payload", {}) or {})
    vector_obj = getattr(point, "vector", {})
    vector: object
    if isinstance(vector_obj, Mapping):
        vector = vector_obj.get(vector_name, ())
    else:
        vector = vector_obj
    return point_from_payload(
        point_id=str(getattr(point, "id")),
        vector=tuple(float(item) for item in cast(Sequence[float], vector)),
        payload=payload,
    )


def _extract_vectors_config(info: object) -> dict[str, dict[str, object]]:
    raw = _to_mapping(info)
    config = _safe_mapping(raw.get("config"))
    params = _safe_mapping(config.get("params"))
    vectors = params.get("vectors")
    if isinstance(vectors, Mapping):
        return {str(name): _safe_mapping(value) for name, value in vectors.items()}
    params_obj = getattr(getattr(info, "config", None), "params", None)
    vectors_obj = getattr(params_obj, "vectors", None)
    if isinstance(vectors_obj, Mapping):
        return {str(name): _to_mapping(value) for name, value in vectors_obj.items()}
    return {}


def _normalize_distance(distance: str) -> WorkingMemoryDistance:
    normalized = distance.split(".")[-1].lower()
    if normalized == "cosine":
        return "Cosine"
    if normalized == "dot":
        return "Dot"
    if normalized == "euclid":
        return "Euclid"
    if normalized == "manhattan":
        return "Manhattan"
    raise ValueError("unsupported working memory distance")


def _to_mapping(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        dumped = cast(Any, value).model_dump(mode="json", exclude_none=True)
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_mapping(value: object) -> dict[str, object]:
    return _to_mapping(value)
