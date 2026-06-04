from __future__ import annotations

from uuid import uuid4

from backend.rag.cache.cache_config import CacheSettings
from backend.rag.cache.cache_layer import build_cache_payload
from backend.rag.cache.cache_models import CacheFingerprint, RetrievalResult


def _fingerprint() -> CacheFingerprint:
    return CacheFingerprint(
        profile_name="default",
        embedding_model="qwen3-embedding",
        embedding_dim=4,
        source_collection="quimera_knowledge",
        corpus_epoch="dev",
        retrieval_fingerprint="a" * 64,
    )


def test_cache_payload_excludes_sensitive_fields() -> None:
    result = RetrievalResult(
        doc_ids=("doc-1",),
        scores=(0.9,),
        fusion_backend="python_rrf",
        profile_name="default",
        retrieval_fingerprint="a" * 64,
        metadata={"safe": True},
    )
    entry_payload = build_cache_payload(
        cache_id=uuid4(),
        result=result,
        fingerprint=_fingerprint(),
        settings=CacheSettings(vector_size=4),
    )
    forbidden = {
        "query_text",
        "raw_query",
        "answer",
        "response",
        "prompt",
        "chunks",
        "chunk_text",
        "secret",
        "api_key",
        "token",
        "embedding",
        "vector",
    }

    assert forbidden.isdisjoint(entry_payload)
    assert forbidden.isdisjoint(entry_payload["metadata"])


def test_settings_repr_does_not_leak_api_key() -> None:
    settings = CacheSettings()

    assert "api_key" not in repr(settings).lower()
