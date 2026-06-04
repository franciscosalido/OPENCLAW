"""Immutable models for the HybridRAG semantic retrieval cache."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from backend.rag.cache.types import CacheFilterValue


SCHEMA_VERSION_QUERY_CACHE_V1 = "query-cache-v1"
FusionBackend = Literal["python_rrf", "qdrant_rrf"]
CacheDistance = Literal["Cosine", "Dot", "Euclid", "Manhattan"]
FORBIDDEN_CACHE_PAYLOAD_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "query_text",
        "raw_query",
        "answer",
        "response",
        "chunks",
        "chunk_text",
        "secret",
        "api_key",
        "token",
        "embedding",
        "vector",
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheFingerprint:
    """Versioned retrieval-cache fingerprint."""

    profile_name: str
    embedding_model: str
    embedding_dim: int
    source_collection: str
    corpus_epoch: str
    retrieval_fingerprint: str
    schema_version: str = SCHEMA_VERSION_QUERY_CACHE_V1

    def __post_init__(self) -> None:
        for field_name in (
            "profile_name",
            "embedding_model",
            "source_collection",
            "corpus_epoch",
            "retrieval_fingerprint",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.embedding_dim <= 0:
            raise ValueError("embedding_dim must be > 0")
        if self.schema_version != SCHEMA_VERSION_QUERY_CACHE_V1:
            raise ValueError("schema_version must be query-cache-v1")

    def to_payload_filter_conditions(self) -> dict[str, CacheFilterValue]:
        """Return payload fields that must match this fingerprint."""

        return {
            "schema_version": self.schema_version,
            "profile_name": self.profile_name,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "source_collection": self.source_collection,
            "corpus_epoch": self.corpus_epoch,
            "retrieval_fingerprint": self.retrieval_fingerprint,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalResult:
    """Safe retrieval result value that may be cached."""

    doc_ids: tuple[str, ...]
    scores: tuple[float, ...]
    fusion_backend: FusionBackend
    profile_name: str
    retrieval_fingerprint: str
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.doc_ids:
            raise ValueError("doc_ids cannot be empty")
        if not self.scores:
            raise ValueError("scores cannot be empty")
        if len(self.doc_ids) != len(self.scores):
            raise ValueError("doc_ids and scores must have the same length")
        for doc_id in self.doc_ids:
            _require_non_empty(doc_id, "doc_ids")
        for score in self.scores:
            _require_finite_number(score, "scores")
        if self.fusion_backend not in ("python_rrf", "qdrant_rrf"):
            raise ValueError("fusion_backend must be python_rrf or qdrant_rrf")
        _require_non_empty(self.profile_name, "profile_name")
        _require_non_empty(self.retrieval_fingerprint, "retrieval_fingerprint")
        if self.metadata is not None:
            _validate_safe_mapping(self.metadata, "metadata")
            object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheEntry:
    """Record stored in Qdrant cache collection."""

    cache_id: UUID
    query_vector: tuple[float, ...]
    result_doc_ids: tuple[str, ...]
    result_scores: tuple[float, ...]
    fusion_backend: FusionBackend
    fingerprint: CacheFingerprint
    created_at: datetime
    expires_at: datetime | None = None
    hit_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.cache_id, UUID):
            raise TypeError("cache_id must be a UUID")
        _validate_vector(self.query_vector, "query_vector")
        _validate_result_lists(self.result_doc_ids, self.result_scores)
        if self.fusion_backend not in ("python_rrf", "qdrant_rrf"):
            raise ValueError("fusion_backend must be python_rrf or qdrant_rrf")
        if not isinstance(self.fingerprint, CacheFingerprint):
            raise TypeError("fingerprint must be CacheFingerprint")
        _require_tzaware(self.created_at, "created_at")
        if self.expires_at is not None:
            _require_tzaware(self.expires_at, "expires_at")
            if self.expires_at <= self.created_at:
                raise ValueError("expires_at must be greater than created_at")
        if self.hit_count < 0:
            raise ValueError("hit_count must be >= 0")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether the entry has expired."""

        if self.expires_at is None:
            return False
        resolved_now = now or datetime.now(UTC)
        _require_tzaware(resolved_now, "now")
        return self.expires_at <= resolved_now


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheHit:
    """Lightweight cache lookup hit."""

    cache_id: UUID
    similarity_score: float
    result_doc_ids: tuple[str, ...]
    result_scores: tuple[float, ...]
    fusion_backend: FusionBackend
    fingerprint: CacheFingerprint
    created_at: datetime
    expires_at: datetime | None
    hit_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.cache_id, UUID):
            raise TypeError("cache_id must be a UUID")
        if not 0.0 <= self.similarity_score <= 1.0:
            raise ValueError("similarity_score must be between 0.0 and 1.0")
        _validate_result_lists(self.result_doc_ids, self.result_scores)
        _require_tzaware(self.created_at, "created_at")
        if self.expires_at is not None:
            _require_tzaware(self.expires_at, "expires_at")
        if self.hit_count < 0:
            raise ValueError("hit_count must be >= 0")


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheInvalidationResult:
    """Result of a cache invalidation operation."""

    matched_count: int | None
    deleted_count: int | None
    selector_kind: str
    dry_run: bool

    def __post_init__(self) -> None:
        if self.matched_count is not None and self.matched_count < 0:
            raise ValueError("matched_count must be >= 0")
        if self.deleted_count is not None and self.deleted_count < 0:
            raise ValueError("deleted_count must be >= 0")
        _require_non_empty(self.selector_kind, "selector_kind")


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow safe metadata dict."""

    if metadata is None:
        return {}
    _validate_safe_mapping(metadata, "metadata")
    return dict(metadata)


def _validate_result_lists(doc_ids: tuple[str, ...], scores: tuple[float, ...]) -> None:
    if not doc_ids:
        raise ValueError("result_doc_ids cannot be empty")
    if len(doc_ids) != len(scores):
        raise ValueError("result_doc_ids and result_scores must have the same length")
    for doc_id in doc_ids:
        _require_non_empty(doc_id, "result_doc_ids")
    for score in scores:
        _require_finite_number(score, "result_scores")


def _validate_vector(vector: tuple[float, ...], field_name: str) -> None:
    if not vector:
        raise ValueError(f"{field_name} cannot be empty")
    for item in vector:
        _require_finite_number(item, field_name)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_finite_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must contain only finite values")


def _require_tzaware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validate_safe_mapping(value: Mapping[str, Any], field_name: str) -> None:
    for key in value:
        if str(key).casefold() in FORBIDDEN_CACHE_PAYLOAD_KEYS:
            raise ValueError(f"{field_name} contains sensitive cache payload key")
