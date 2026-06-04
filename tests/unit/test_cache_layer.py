from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.cache_layer import CacheLayer
from backend.rag.cache.cache_models import CacheFingerprint, RetrievalResult
from backend.rag.cache.errors import CachePayloadError, CacheVectorDimensionError


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


class FakePoint:
    def __init__(self, *, point_id: str, score: float, payload: dict[str, object]) -> None:
        self.id = point_id
        self.score = score
        self.payload = payload


class FakeQueryResult:
    def __init__(self, points: list[FakePoint]) -> None:
        self.points = points


class FakeCountResult:
    def __init__(self, count: int) -> None:
        self.count = count


class FakeQdrantClient:
    def __init__(self) -> None:
        self.points: dict[str, dict[str, object]] = {}
        self.query_calls: list[dict[str, object]] = []
        self.upserts: list[object] = []
        self.deletes: list[object] = []
        self.set_payload_fail = False

    async def query_points(self, **kwargs: object) -> FakeQueryResult:
        self.query_calls.append(dict(kwargs))
        points = [
            FakePoint(
                point_id=point_id,
                score=float(payload.get("_score", 0.99)),
                payload={key: value for key, value in payload.items() if key != "_score"},
            )
            for point_id, payload in self.points.items()
        ]
        return FakeQueryResult(points[: int(kwargs["limit"])])

    async def upsert(self, **kwargs: object) -> None:
        self.upserts.append(kwargs["points"])

    async def count(self, **kwargs: object) -> FakeCountResult:
        return FakeCountResult(len(self.points))

    async def delete(self, **kwargs: object) -> None:
        self.deletes.append(kwargs["points_selector"])

    async def scroll(self, **kwargs: object) -> tuple[list[FakePoint], None]:
        points = [
            FakePoint(point_id=point_id, score=0.99, payload=payload)
            for point_id, payload in self.points.items()
        ]
        return points, None

    async def set_payload(self, **kwargs: object) -> None:
        if self.set_payload_fail:
            raise RuntimeError("boom")


def _fingerprint() -> CacheFingerprint:
    return CacheFingerprint(
        profile_name="default",
        embedding_model="qwen3-embedding",
        embedding_dim=4,
        source_collection="quimera_knowledge",
        corpus_epoch="dev",
        retrieval_fingerprint="a" * 64,
    )


def _result(**overrides: object) -> RetrievalResult:
    values = {
        "doc_ids": ("doc-1", "doc-2"),
        "scores": (0.9, 0.8),
        "fusion_backend": "python_rrf",
        "profile_name": "default",
        "retrieval_fingerprint": "a" * 64,
        "metadata": {"safe": True},
    }
    values.update(overrides)
    return RetrievalResult(**values)  # type: ignore[arg-type]


def _settings(**overrides: object) -> CacheSettings:
    values = {"vector_size": 4, "threshold": 0.9}
    values.update(overrides)
    return CacheSettings(**values)


@pytest.mark.asyncio
async def test_disabled_lookup_returns_none_without_qdrant_call() -> None:
    client = FakeQdrantClient()
    layer = CacheLayer(client, _settings(enabled=False))

    assert await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint()) is None
    assert client.query_calls == []


@pytest.mark.asyncio
async def test_lookup_miss_and_below_threshold_return_none() -> None:
    client = FakeQdrantClient()
    layer = CacheLayer(client, _settings())

    assert await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint()) is None
    client.points[str(uuid4())] = _payload(_score=0.5)
    assert await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint()) is None


@pytest.mark.asyncio
async def test_lookup_hit_uses_filter_and_no_vectors() -> None:
    cache_id = uuid4()
    client = FakeQdrantClient()
    client.points[str(cache_id)] = _payload(_score=0.95)
    layer = CacheLayer(client, _settings())

    hit = await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint())

    assert hit is not None
    assert hit.cache_id == cache_id
    call = client.query_calls[-1]
    assert call["with_payload"] is True
    assert call["with_vectors"] is False
    assert call["query_filter"] is not None


@pytest.mark.asyncio
async def test_lookup_rejects_bad_payload_and_expired_payload() -> None:
    client = FakeQdrantClient()
    client.points[str(uuid4())] = {"schema_version": "wrong", "_score": 0.95}
    layer = CacheLayer(client, _settings())
    with pytest.raises(CachePayloadError):
        await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint())

    client.points = {str(uuid4()): _payload(expires_at=(NOW - timedelta(seconds=1)).isoformat(), _score=0.95)}
    assert await layer.lookup(query_vector=(0.1, 0.2, 0.3, 0.4), fingerprint=_fingerprint()) is None


@pytest.mark.asyncio
async def test_store_writes_vector_not_payload_and_validates_size() -> None:
    client = FakeQdrantClient()
    layer = CacheLayer(client, _settings(default_ttl_seconds=60))

    entry = await layer.store(
        query_vector=(0.1, 0.2, 0.3, 0.4),
        result=_result(),
        fingerprint=_fingerprint(),
    )

    assert entry is not None
    points = client.upserts[-1]
    point = points[0]  # type: ignore[index]
    assert point.vector == [0.1, 0.2, 0.3, 0.4]
    assert "query_vector" not in point.payload
    assert "vector" not in point.payload
    assert point.payload["schema_version"] == "query-cache-v1"
    with pytest.raises(CacheVectorDimensionError):
        await layer.store(query_vector=(0.1,), result=_result(), fingerprint=_fingerprint())


@pytest.mark.asyncio
async def test_store_rejects_too_many_docs_and_sensitive_metadata() -> None:
    layer = CacheLayer(FakeQdrantClient(), _settings(max_result_docs=1))

    with pytest.raises(ValueError, match="max_result_docs"):
        await layer.store(query_vector=(0.1, 0.2, 0.3, 0.4), result=_result(), fingerprint=_fingerprint())
    with pytest.raises(ValueError, match="metadata"):
        _result(metadata={"secret": "bad"})


@pytest.mark.asyncio
async def test_invalidation_hot_entries_and_record_hit() -> None:
    cache_id = uuid4()
    client = FakeQdrantClient()
    client.points[str(cache_id)] = _payload(hit_count=5, _score=0.99)
    client.points[str(uuid4())] = _payload(hit_count=2, _score=0.99)
    layer = CacheLayer(client, _settings())

    dry = await layer.invalidate_by_schema_version("query-cache-v1", dry_run=True)
    deleted = await layer.invalidate_by_fingerprint(_fingerprint())
    entries = await layer.get_hot_entries(top_n=2)
    await layer.record_hit(cache_id=cache_id, current_hit_count=5)
    client.set_payload_fail = True
    await layer.record_hit(cache_id=cache_id, current_hit_count=5)

    assert dry.dry_run is True
    assert dry.matched_count == 2
    assert deleted.dry_run is False
    assert entries[0].hit_count >= entries[1].hit_count
    assert client.deletes


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "result_doc_ids": ["doc-1", "doc-2"],
        "result_scores": [0.9, 0.8],
        "fusion_backend": "python_rrf",
        "profile_name": "default",
        "embedding_model": "qwen3-embedding",
        "embedding_dim": 4,
        "source_collection": "quimera_knowledge",
        "corpus_epoch": "dev",
        "retrieval_fingerprint": "a" * 64,
        "schema_version": "query-cache-v1",
        "created_at": NOW.isoformat(),
        "expires_at": None,
        "hit_count": 0,
        "metadata": {"safe": True},
    }
    payload.update(overrides)
    return payload
