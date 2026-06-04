from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from backend.rag.cache.cache_collection import CacheCollectionManager
from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.errors import CacheCollectionMismatchError


pytestmark = pytest.mark.integration


def _qdrant_url() -> str | None:
    return os.environ.get("TEST_QDRANT_URL") or os.environ.get("QUIMERA_QDRANT_URL")


@pytest.fixture
async def qdrant_client() -> AsyncGenerator[tuple[AsyncQdrantClient, str], None]:
    url = _qdrant_url()
    if not url:
        pytest.skip("TEST_QDRANT_URL or QUIMERA_QDRANT_URL is required")
    collection = f"quimera_query_cache_test_{uuid4().hex}"
    client = AsyncQdrantClient(url=url)
    try:
        yield client, collection
    finally:
        if collection.startswith("quimera_query_cache_test_"):
            exists = await client.collection_exists(collection)
            if exists:
                await client.delete_collection(collection)
        await client.close()


async def test_qdrant_cache_collection_lifecycle(
    qdrant_client: tuple[AsyncQdrantClient, str],
) -> None:
    client, collection = qdrant_client
    settings = CacheSettings(collection_name=collection, vector_size=4)
    manager = CacheCollectionManager(client, settings)

    await manager.ensure_collection()
    await manager.ensure_collection()
    await manager.ensure_payload_indexes()
    info = await client.get_collection(collection)

    assert info is not None


async def test_qdrant_cache_collection_mismatch_fails(
    qdrant_client: tuple[AsyncQdrantClient, str],
) -> None:
    client, collection = qdrant_client
    await client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.DOT),
    )
    manager = CacheCollectionManager(
        client,
        CacheSettings(collection_name=collection, vector_size=4),
    )

    with pytest.raises(CacheCollectionMismatchError):
        await manager.ensure_collection()
