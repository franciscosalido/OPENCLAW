from __future__ import annotations

import pytest

from backend.rag.cache.cache_collection import (
    CACHE_PAYLOAD_INDEXES,
    CacheCollectionManager,
    qdrant_distance,
)
from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.errors import CacheCollectionMismatchError


class FakeQdrantClient:
    def __init__(self) -> None:
        self.exists = False
        self.collection_info: dict[str, object] = {}
        self.created: list[dict[str, object]] = []
        self.indexes: list[tuple[str, object]] = []
        self.recreated = False
        self.deleted = False

    async def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    async def create_collection(self, **kwargs: object) -> None:
        self.created.append(dict(kwargs))
        self.exists = True
        self.collection_info = {"size": 1024, "distance": "Cosine"}

    async def get_collection(self, collection_name: str) -> dict[str, object]:
        return self.collection_info

    async def create_payload_index(self, **kwargs: object) -> None:
        self.indexes.append((str(kwargs["field_name"]), kwargs["field_schema"]))

    async def recreate_collection(self, *args: object, **kwargs: object) -> None:
        self.recreated = True

    async def delete_collection(self, *args: object, **kwargs: object) -> None:
        self.deleted = True


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_absent() -> None:
    client = FakeQdrantClient()
    manager = CacheCollectionManager(client, CacheSettings())

    await manager.ensure_collection()

    assert client.created
    assert client.created[0]["collection_name"] == "quimera_query_cache"
    assert client.recreated is False
    assert client.deleted is False


@pytest.mark.asyncio
async def test_ensure_collection_validates_existing_collection() -> None:
    client = FakeQdrantClient()
    client.exists = True
    client.collection_info = {"size": 1024, "distance": "Cosine"}
    manager = CacheCollectionManager(client, CacheSettings())

    await manager.ensure_collection()

    assert client.created == []


@pytest.mark.asyncio
async def test_collection_mismatch_fails_closed() -> None:
    client = FakeQdrantClient()
    client.exists = True
    client.collection_info = {"size": 768, "distance": "Dot"}
    manager = CacheCollectionManager(client, CacheSettings())

    with pytest.raises(CacheCollectionMismatchError):
        await manager.ensure_collection()


@pytest.mark.asyncio
async def test_payload_indexes_are_created() -> None:
    client = FakeQdrantClient()
    manager = CacheCollectionManager(client, CacheSettings())

    await manager.ensure_payload_indexes()

    assert {name for name, _ in client.indexes} == set(CACHE_PAYLOAD_INDEXES)


def test_distance_mapping() -> None:
    assert qdrant_distance("Cosine").value == "Cosine"
    assert qdrant_distance("Dot").value == "Dot"
    with pytest.raises(ValueError):
        qdrant_distance("Bad")  # type: ignore[arg-type]
