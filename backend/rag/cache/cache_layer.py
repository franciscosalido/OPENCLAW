"""Async Qdrant-backed semantic retrieval cache layer."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from backend.rag.cache.cache_collection import CacheCollectionManager
from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.cache_models import (
    SCHEMA_VERSION_QUERY_CACHE_V1,
    CacheEntry,
    CacheFingerprint,
    CacheHit,
    CacheInvalidationResult,
    RetrievalResult,
    sanitize_metadata,
)
from backend.rag.cache.errors import CachePayloadError, CacheVectorDimensionError


class CacheLayer:
    """Plug-in semantic retrieval cache over a dedicated Qdrant collection."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        settings: CacheSettings,
        collection_manager: CacheCollectionManager | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._collection_manager = collection_manager or CacheCollectionManager(
            client,
            settings,
        )

    def is_enabled(self) -> bool:
        """Return whether cache is enabled."""

        return self._settings.enabled

    async def ensure_ready(self) -> None:
        """Ensure the cache collection and indexes exist."""

        if not self.is_enabled():
            return
        await self._collection_manager.ensure_collection()

    async def lookup(
        self,
        *,
        query_vector: Sequence[float],
        fingerprint: CacheFingerprint,
    ) -> CacheHit | None:
        """Return a cache hit for a semantically equivalent query, if present."""

        if not self.is_enabled():
            return None
        vector = _validate_query_vector(query_vector, self._settings.vector_size)
        result = await self._client.query_points(
            collection_name=self._settings.collection_name,
            query=vector,
            query_filter=_filter_for_fingerprint(fingerprint),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        points = list(getattr(result, "points", []))
        if not points:
            return None
        point = points[0]
        score = float(getattr(point, "score", 0.0))
        if score < self._settings.threshold:
            return None
        hit = _cache_hit_from_point(point, score=score)
        if _is_hit_expired(hit):
            return None
        await self.record_hit(cache_id=hit.cache_id, current_hit_count=hit.hit_count)
        return hit

    async def store(
        self,
        *,
        query_vector: Sequence[float],
        result: RetrievalResult,
        fingerprint: CacheFingerprint,
        cache_id: UUID | None = None,
    ) -> CacheEntry | None:
        """Store a retrieval result. Returns None when cache is disabled."""

        if not self.is_enabled():
            return None
        if len(result.doc_ids) > self._settings.max_result_docs:
            raise ValueError("result has more docs than max_result_docs")
        resolved_cache_id = cache_id or uuid4()
        vector = _validate_query_vector(query_vector, self._settings.vector_size)
        created_at = datetime.now(UTC)
        expires_at = (
            created_at + timedelta(seconds=self._settings.default_ttl_seconds)
            if self._settings.default_ttl_seconds is not None
            else None
        )
        entry = CacheEntry(
            cache_id=resolved_cache_id,
            query_vector=tuple(vector),
            result_doc_ids=result.doc_ids,
            result_scores=result.scores,
            fusion_backend=result.fusion_backend,
            fingerprint=fingerprint,
            created_at=created_at,
            expires_at=expires_at,
            hit_count=0,
        )
        payload = build_cache_payload(
            cache_id=resolved_cache_id,
            result=result,
            fingerprint=fingerprint,
            settings=self._settings,
            created_at=created_at,
            expires_at=expires_at,
        )
        point = models.PointStruct(
            id=str(resolved_cache_id),
            vector=vector,
            payload=payload,
        )
        await self._client.upsert(
            collection_name=self._settings.collection_name,
            points=[point],
            wait=True,
        )
        return entry

    async def invalidate_by_schema_version(
        self,
        version: str,
        *,
        dry_run: bool = False,
    ) -> CacheInvalidationResult:
        return await self._invalidate(
            _filter_from_mapping({"schema_version": version}),
            selector_kind="schema_version",
            dry_run=dry_run,
        )

    async def invalidate_by_fingerprint(
        self,
        fingerprint: CacheFingerprint,
        *,
        dry_run: bool = False,
    ) -> CacheInvalidationResult:
        return await self._invalidate(
            _filter_for_fingerprint(fingerprint),
            selector_kind="fingerprint",
            dry_run=dry_run,
        )

    async def invalidate_by_corpus_epoch(
        self,
        corpus_epoch: str,
        *,
        dry_run: bool = False,
    ) -> CacheInvalidationResult:
        return await self._invalidate(
            _filter_from_mapping({"corpus_epoch": corpus_epoch}),
            selector_kind="corpus_epoch",
            dry_run=dry_run,
        )

    async def invalidate_expired(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> CacheInvalidationResult:
        resolved_now = now or datetime.now(UTC)
        return await self._invalidate(
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="expires_at",
                        range=models.DatetimeRange(lte=resolved_now),
                    )
                ]
            ),
            selector_kind="expired",
            dry_run=dry_run,
        )

    async def get_hot_entries(
        self,
        *,
        top_n: int = 100,
    ) -> list[CacheHit]:
        """Return hot cache entries sorted by hit count descending."""

        if top_n <= 0:
            raise ValueError("top_n must be > 0")
        limit = top_n * self._settings.hot_entries_oversample_factor
        points, _ = await self._client.scroll(
            collection_name=self._settings.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        hits = [
            _cache_hit_from_point(point, score=float(getattr(point, "score", 1.0)))
            for point in points
        ]
        active = [hit for hit in hits if not _is_hit_expired(hit)]
        return sorted(active, key=lambda hit: hit.hit_count, reverse=True)[:top_n]

    async def record_hit(
        self,
        *,
        cache_id: UUID,
        current_hit_count: int | None = None,
    ) -> None:
        """Best-effort hit counter update."""

        if current_hit_count is None:
            return
        try:
            await self._client.set_payload(
                collection_name=self._settings.collection_name,
                payload={"hit_count": current_hit_count + 1},
                points=[str(cache_id)],
                wait=True,
            )
        except Exception:
            return

    async def _invalidate(
        self,
        query_filter: models.Filter,
        *,
        selector_kind: str,
        dry_run: bool,
    ) -> CacheInvalidationResult:
        count = await self._client.count(
            collection_name=self._settings.collection_name,
            count_filter=query_filter,
            exact=True,
        )
        matched = int(getattr(count, "count", 0))
        if dry_run:
            return CacheInvalidationResult(
                matched_count=matched,
                deleted_count=None,
                selector_kind=selector_kind,
                dry_run=True,
            )
        await self._client.delete(
            collection_name=self._settings.collection_name,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )
        return CacheInvalidationResult(
            matched_count=matched,
            deleted_count=matched,
            selector_kind=selector_kind,
            dry_run=False,
        )


def build_cache_payload(
    *,
    cache_id: UUID,
    result: RetrievalResult,
    fingerprint: CacheFingerprint,
    settings: CacheSettings,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Build safe Qdrant payload for one cache entry."""

    resolved_created_at = created_at or datetime.now(UTC)
    resolved_expires_at = expires_at
    if resolved_expires_at is None and settings.default_ttl_seconds is not None:
        resolved_expires_at = resolved_created_at + timedelta(
            seconds=settings.default_ttl_seconds
        )
    metadata = sanitize_metadata(result.metadata)
    return {
        "cache_id": str(cache_id),
        "result_doc_ids": list(result.doc_ids),
        "result_scores": list(result.scores),
        "fusion_backend": result.fusion_backend,
        "profile_name": fingerprint.profile_name,
        "embedding_model": fingerprint.embedding_model,
        "embedding_dim": fingerprint.embedding_dim,
        "source_collection": fingerprint.source_collection,
        "corpus_epoch": fingerprint.corpus_epoch,
        "retrieval_fingerprint": fingerprint.retrieval_fingerprint,
        "schema_version": SCHEMA_VERSION_QUERY_CACHE_V1,
        "created_at": resolved_created_at.isoformat(),
        "expires_at": resolved_expires_at.isoformat() if resolved_expires_at else None,
        "hit_count": 0,
        "metadata": metadata,
    }


def _validate_query_vector(vector: Sequence[float], expected_size: int) -> list[float]:
    values = [float(item) for item in vector]
    if not values:
        raise CacheVectorDimensionError("query_vector cannot be empty")
    if len(values) != expected_size:
        raise CacheVectorDimensionError("query_vector dimension mismatch")
    if any(not math.isfinite(item) for item in values):
        raise CacheVectorDimensionError("query_vector must contain only finite values")
    return values


def _filter_for_fingerprint(fingerprint: CacheFingerprint) -> models.Filter:
    return _filter_from_mapping(fingerprint.to_payload_filter_conditions())


def _filter_from_mapping(values: Mapping[str, object]) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=key,
                match=models.MatchValue(value=value),
            )
            for key, value in values.items()
        ]
    )


def _cache_hit_from_point(point: object, *, score: float) -> CacheHit:
    payload = getattr(point, "payload", None)
    if not isinstance(payload, Mapping):
        raise CachePayloadError("cache payload is missing")
    if payload.get("schema_version") != SCHEMA_VERSION_QUERY_CACHE_V1:
        raise CachePayloadError("cache payload schema_version is invalid")
    try:
        cache_id = UUID(str(getattr(point, "id", payload.get("cache_id"))))
        fingerprint = CacheFingerprint(
            profile_name=str(payload["profile_name"]),
            embedding_model=str(payload["embedding_model"]),
            embedding_dim=int(payload["embedding_dim"]),
            source_collection=str(payload["source_collection"]),
            corpus_epoch=str(payload["corpus_epoch"]),
            retrieval_fingerprint=str(payload["retrieval_fingerprint"]),
            schema_version=str(payload["schema_version"]),
        )
        doc_ids = tuple(str(item) for item in _sequence_payload(payload, "result_doc_ids"))
        scores = tuple(float(item) for item in _sequence_payload(payload, "result_scores"))
        created_at = _parse_datetime(payload["created_at"], "created_at")
        expires_at_raw = payload.get("expires_at")
        expires_at = (
            None
            if expires_at_raw is None
            else _parse_datetime(expires_at_raw, "expires_at")
        )
        return CacheHit(
            cache_id=cache_id,
            similarity_score=score,
            result_doc_ids=doc_ids,
            result_scores=scores,
            fusion_backend=cast(Any, payload["fusion_backend"]),
            fingerprint=fingerprint,
            created_at=created_at,
            expires_at=expires_at,
            hit_count=int(payload.get("hit_count", 0)),
        )
    except CachePayloadError:
        raise
    except Exception as exc:
        raise CachePayloadError("cache payload is malformed") from exc


def _sequence_payload(payload: Mapping[str, object], key: str) -> Sequence[object]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CachePayloadError("cache payload sequence field is malformed")
    return value


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise CachePayloadError(f"cache payload {field_name} is malformed")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CachePayloadError(f"cache payload {field_name} is timezone-naive")
    return parsed


def _is_hit_expired(hit: CacheHit) -> bool:
    return hit.expires_at is not None and hit.expires_at <= datetime.now(UTC)
