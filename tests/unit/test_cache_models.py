from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.rag.cache.cache_models import (
    SCHEMA_VERSION_QUERY_CACHE_V1,
    CacheEntry,
    CacheFingerprint,
    CacheHit,
    RetrievalResult,
)


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def _fingerprint() -> CacheFingerprint:
    return CacheFingerprint(
        profile_name="default",
        embedding_model="qwen3-embedding",
        embedding_dim=1024,
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


def _entry(**overrides: object) -> CacheEntry:
    values = {
        "cache_id": uuid4(),
        "query_vector": (0.1, 0.2),
        "result_doc_ids": ("doc-1",),
        "result_scores": (0.9,),
        "fusion_backend": "python_rrf",
        "fingerprint": _fingerprint(),
        "created_at": NOW,
    }
    values.update(overrides)
    return CacheEntry(**values)  # type: ignore[arg-type]


def test_cache_dataclasses_are_frozen_and_slots() -> None:
    entry = _entry()

    assert is_dataclass(entry)
    assert hasattr(CacheEntry, "__slots__")
    assert hasattr(CacheHit, "__slots__")
    with pytest.raises(FrozenInstanceError):
        entry.hit_count = 10  # type: ignore[misc]


def test_cache_fingerprint_validation() -> None:
    with pytest.raises(ValueError, match="profile_name"):
        CacheFingerprint(
            profile_name=" ",
            embedding_model="qwen3",
            embedding_dim=1024,
            source_collection="source",
            corpus_epoch="dev",
            retrieval_fingerprint="hash",
        )
    with pytest.raises(ValueError, match="embedding_dim"):
        CacheFingerprint(
            profile_name="default",
            embedding_model="qwen3",
            embedding_dim=0,
            source_collection="source",
            corpus_epoch="dev",
            retrieval_fingerprint="hash",
        )
    with pytest.raises(ValueError, match="schema_version"):
        CacheFingerprint(
            profile_name="default",
            embedding_model="qwen3",
            embedding_dim=1024,
            source_collection="source",
            corpus_epoch="dev",
            retrieval_fingerprint="hash",
            schema_version="v2",
        )


def test_retrieval_result_validation() -> None:
    with pytest.raises(ValueError, match="same length"):
        _result(scores=(0.1,))
    with pytest.raises(ValueError, match="doc_ids"):
        _result(doc_ids=("",))
    with pytest.raises(ValueError, match="scores"):
        _result(scores=(math.nan, math.inf))
    with pytest.raises(ValueError, match="metadata"):
        _result(metadata={"prompt": "secret"})


def test_cache_entry_validation_and_expiry() -> None:
    with pytest.raises(ValueError, match="query_vector"):
        _entry(query_vector=())
    with pytest.raises(ValueError, match="query_vector"):
        _entry(query_vector=(math.nan,))
    with pytest.raises(ValueError, match="created_at"):
        _entry(created_at=datetime(2026, 6, 4))
    with pytest.raises(ValueError, match="expires_at"):
        _entry(expires_at=NOW)

    entry = _entry(expires_at=NOW + timedelta(seconds=1))
    assert entry.is_expired(NOW) is False
    assert entry.is_expired(NOW + timedelta(seconds=2)) is True


def test_cache_hit_validation() -> None:
    entry = _entry()
    hit = CacheHit(
        cache_id=entry.cache_id,
        similarity_score=0.95,
        result_doc_ids=entry.result_doc_ids,
        result_scores=entry.result_scores,
        fusion_backend=entry.fusion_backend,
        fingerprint=entry.fingerprint,
        created_at=entry.created_at,
        expires_at=entry.expires_at,
        hit_count=entry.hit_count,
    )

    assert hit.fingerprint.schema_version == SCHEMA_VERSION_QUERY_CACHE_V1
    with pytest.raises(ValueError, match="similarity_score"):
        CacheHit(
            cache_id=entry.cache_id,
            similarity_score=1.5,
            result_doc_ids=entry.result_doc_ids,
            result_scores=entry.result_scores,
            fusion_backend=entry.fusion_backend,
            fingerprint=entry.fingerprint,
            created_at=entry.created_at,
            expires_at=entry.expires_at,
            hit_count=entry.hit_count,
        )
