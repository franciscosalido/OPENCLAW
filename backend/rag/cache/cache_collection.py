"""Qdrant collection management for the semantic retrieval cache."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from qdrant_client.http import models

from backend.rag.cache.cache_config import CacheDistance, CacheSettings
from backend.rag.cache.errors import CacheCollectionMismatchError


CACHE_PAYLOAD_INDEXES: Mapping[str, models.PayloadSchemaType] = {
    "schema_version": models.PayloadSchemaType.KEYWORD,
    "profile_name": models.PayloadSchemaType.KEYWORD,
    "embedding_model": models.PayloadSchemaType.KEYWORD,
    "source_collection": models.PayloadSchemaType.KEYWORD,
    "corpus_epoch": models.PayloadSchemaType.KEYWORD,
    "retrieval_fingerprint": models.PayloadSchemaType.KEYWORD,
    "hit_count": models.PayloadSchemaType.INTEGER,
    "created_at": models.PayloadSchemaType.DATETIME,
    "expires_at": models.PayloadSchemaType.DATETIME,
}


class CacheCollectionManager:
    """Create and validate the dedicated Qdrant cache collection."""

    def __init__(self, client: Any, settings: CacheSettings) -> None:
        self._client = client
        self._settings = settings

    async def ensure_collection(self) -> None:
        """Create collection if absent, otherwise validate compatibility."""

        if await self.collection_exists():
            await self.assert_collection_compatible()
        else:
            await self._client.create_collection(
                collection_name=self._settings.collection_name,
                vectors_config=models.VectorParams(
                    size=self._settings.vector_size,
                    distance=qdrant_distance(self._settings.distance),
                ),
            )
        await self.ensure_payload_indexes()

    async def collection_exists(self) -> bool:
        """Return whether the configured cache collection exists."""

        return bool(
            await self._client.collection_exists(
                collection_name=self._settings.collection_name
            )
        )

    async def assert_collection_compatible(self) -> None:
        """Raise if the existing collection does not match cache settings."""

        info = await self._client.get_collection(
            collection_name=self._settings.collection_name
        )
        vector_size, distance = _extract_unnamed_vector_config(info)
        if vector_size != self._settings.vector_size:
            raise CacheCollectionMismatchError("cache collection vector size mismatch")
        if _normalize_distance(distance) != self._settings.distance:
            raise CacheCollectionMismatchError("cache collection distance mismatch")

    async def ensure_payload_indexes(self) -> None:
        """Create required payload indexes idempotently."""

        for field_name, field_schema in CACHE_PAYLOAD_INDEXES.items():
            await self._client.create_payload_index(
                collection_name=self._settings.collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )


def qdrant_distance(distance: CacheDistance) -> models.Distance:
    """Map settings distance string to Qdrant enum."""

    if distance == "Cosine":
        return models.Distance.COSINE
    if distance == "Dot":
        return models.Distance.DOT
    if distance == "Euclid":
        return models.Distance.EUCLID
    if distance == "Manhattan":
        return models.Distance.MANHATTAN
    raise ValueError("unsupported cache distance")


def _extract_unnamed_vector_config(info: object) -> tuple[int, str]:
    raw = _model_to_mapping(info)
    if "size" in raw and "distance" in raw:
        return _coerce_int(raw["size"]), str(raw["distance"])
    config = _safe_mapping(raw.get("config"))
    params = _safe_mapping(config.get("params"))
    vectors = params.get("vectors")
    vector_mapping = _safe_mapping(vectors)
    if "size" in vector_mapping and "distance" in vector_mapping:
        return _coerce_int(vector_mapping["size"]), str(vector_mapping["distance"])
    params_obj = getattr(getattr(info, "config", None), "params", None)
    vectors_obj = getattr(params_obj, "vectors", None)
    size = getattr(vectors_obj, "size", None)
    distance = getattr(vectors_obj, "distance", None)
    if size is not None and distance is not None:
        return _coerce_int(size), str(getattr(distance, "value", distance))
    raise CacheCollectionMismatchError("cache collection vector config is missing")


def _normalize_distance(distance: str) -> CacheDistance:
    value = distance.split(".")[-1]
    normalized = value.lower()
    if normalized == "cosine":
        return "Cosine"
    if normalized == "dot":
        return "Dot"
    if normalized == "euclid":
        return "Euclid"
    if normalized == "manhattan":
        return "Manhattan"
    raise CacheCollectionMismatchError("cache collection distance is unsupported")


def _model_to_mapping(model: object) -> Mapping[str, object]:
    if hasattr(model, "model_dump"):
        dumpable = cast(Any, model)
        dumped = dumpable.model_dump(mode="json", exclude_none=True)
        if isinstance(dumped, Mapping):
            return dumped
    if isinstance(model, Mapping):
        return model
    return {}


def _safe_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _coerce_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CacheCollectionMismatchError("cache collection vector size is invalid")
    return value
