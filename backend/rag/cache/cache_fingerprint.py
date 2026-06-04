"""Safe cache fingerprint helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from backend.rag.cache.cache_models import FORBIDDEN_CACHE_PAYLOAD_KEYS


def stable_json_dumps(value: Mapping[str, Any]) -> str:
    """Serialize a mapping deterministically."""

    _reject_sensitive_keys(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(text: str) -> str:
    """Return SHA-256 hex digest."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_retrieval_fingerprint(
    *,
    embedding_model: str,
    embedding_dim: int,
    source_collection: str,
    corpus_epoch: str,
    profile_name: str,
    fusion_backend: str | None = None,
    reranker_name: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Build a stable retrieval fingerprint without storing raw queries."""

    payload: dict[str, Any] = {
        "embedding_dim": embedding_dim,
        "embedding_model": embedding_model,
        "source_collection": source_collection,
        "corpus_epoch": corpus_epoch,
        "profile_name": profile_name,
    }
    if fusion_backend is not None:
        payload["fusion_backend"] = fusion_backend
    if reranker_name is not None:
        payload["reranker_name"] = reranker_name
    if extra:
        _reject_sensitive_keys(extra)
        payload["extra"] = dict(extra)
    return sha256_hex(stable_json_dumps(payload))


def hmac_query_hash(query_text: str, secret: str) -> str:
    """Return HMAC of query text without storing the text itself."""

    if not query_text:
        raise ValueError("query_text cannot be empty")
    if not secret:
        raise ValueError("secret cannot be empty")
    return hmac.new(secret.encode("utf-8"), query_text.encode("utf-8"), hashlib.sha256).hexdigest()


def _reject_sensitive_keys(value: Mapping[str, Any]) -> None:
    for key, item in value.items():
        if str(key).casefold() in FORBIDDEN_CACHE_PAYLOAD_KEYS:
            raise ValueError("sensitive cache fingerprint key is not allowed")
        if isinstance(item, Mapping):
            _reject_sensitive_keys(item)
