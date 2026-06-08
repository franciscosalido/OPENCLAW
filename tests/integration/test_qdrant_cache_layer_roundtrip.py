from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.cache_layer import CacheLayer
from backend.rag.cache.cache_models import CacheFingerprint, RetrievalResult


pytestmark = pytest.mark.integration


def _qdrant_url() -> str | None:
    return os.environ.get("TEST_QDRANT_URL") or os.environ.get("QUIMERA_QDRANT_URL")


@pytest.fixture
async def cache_layer() -> AsyncGenerator[CacheLayer, None]:
    url = _qdrant_url()
    if not url:
        pytest.skip("TEST_QDRANT_URL or QUIMERA_QDRANT_URL is required")
    collection = f"quimera_query_cache_test_{uuid4().hex}"
    client = AsyncQdrantClient(url=url)
    settings = CacheSettings(collection_name=collection, vector_size=4, threshold=0.9)
    layer = CacheLayer(client, settings)
    try:
        await layer.ensure_ready()
        yield layer
    finally:
        if collection.startswith("quimera_query_cache_test_"):
            exists = await client.collection_exists(collection)
            if exists:
                await client.delete_collection(collection)
        await client.close()


def _fingerprint(epoch: str = "dev") -> CacheFingerprint:
    return CacheFingerprint(
        profile_name="default",
        embedding_model="qwen3-embedding",
        embedding_dim=4,
        source_collection="quimera_knowledge",
        corpus_epoch=epoch,
        retrieval_fingerprint="a" * 64,
    )


def _result() -> RetrievalResult:
    return RetrievalResult(
        doc_ids=("doc-1",),
        scores=(0.9,),
        fusion_backend="python_rrf",
        profile_name="default",
        retrieval_fingerprint="a" * 64,
        metadata={"safe": True},
    )


async def test_qdrant_cache_layer_roundtrip(cache_layer: CacheLayer) -> None:
    vector = (0.1, 0.2, 0.3, 0.4)
    fingerprint = _fingerprint()

    entry = await cache_layer.store(
        query_vector=vector,
        result=_result(),
        fingerprint=fingerprint,
    )
    hit = await cache_layer.lookup(query_vector=vector, fingerprint=fingerprint)
    miss = await cache_layer.lookup(
        query_vector=vector, fingerprint=_fingerprint("dev2")
    )
    dry = await cache_layer.invalidate_by_fingerprint(fingerprint, dry_run=True)
    deleted = await cache_layer.invalidate_by_fingerprint(fingerprint)
    after_delete = await cache_layer.lookup(
        query_vector=vector, fingerprint=fingerprint
    )

    assert entry is not None
    assert hit is not None
    assert miss is None
    assert dry.matched_count is not None
    assert deleted.deleted_count is not None
    assert after_delete is None
