"""Safe per-query provenance trace for local RAG runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from backend.rag.collection_guard import (
    EmbeddingDimensionMismatchError,
    load_active_embedding_metadata,
)
from backend.rag.qdrant_store import DEFAULT_COLLECTION_NAME


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"
ALLOWED_TRACE_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING"})
SAFE_GUARD_RESULT_KEYS = frozenset(
    {
        "sampled_count",
        "metadata_absent_count",
        "backend_matches",
        "model_matches",
        "dimensions_match",
        "contract_matches",
        "alias_matches",
    }
)


@dataclass(frozen=True)
class RagTracingConfig:
    """Tracing configuration for safe RAG provenance logs."""

    enabled: bool = True
    log_level: str = "INFO"
    collection_name: str = DEFAULT_COLLECTION_NAME
    embedding_backend: str = "gateway_litellm_current"
    embedding_model: str = "nomic-embed-text"
    embedding_alias: str = "quimera_embed"
    embedding_dimensions: int = 768

    def validated(self) -> RagTracingConfig:
        """Return normalized tracing config or raise ``ValueError``."""
        if not isinstance(self.enabled, bool):
            raise TypeError("rag.tracing.enabled must be boolean")
        log_level = self.log_level.strip().upper()
        if log_level not in ALLOWED_TRACE_LOG_LEVELS:
            raise ValueError(
                "rag.tracing.log_level must be one of "
                f"{sorted(ALLOWED_TRACE_LOG_LEVELS)}"
            )
        collection_name = _validate_non_empty(
            self.collection_name,
            "rag.qdrant.collection",
        )
        embedding_backend = _validate_non_empty(
            self.embedding_backend,
            "rag.embedding.embedding_backend",
        )
        embedding_model = _validate_non_empty(
            self.embedding_model,
            "rag.embedding.embedding_model",
        )
        embedding_alias = _validate_non_empty(
            self.embedding_alias,
            "rag.embedding.embedding_alias",
        )
        if self.embedding_dimensions <= 0:
            raise ValueError("rag.embedding.embedding_dimensions must be greater than zero")
        return RagTracingConfig(
            enabled=self.enabled,
            log_level=log_level,
            collection_name=collection_name,
            embedding_backend=embedding_backend,
            embedding_model=embedding_model,
            embedding_alias=embedding_alias,
            embedding_dimensions=int(self.embedding_dimensions),
        )


@dataclass(frozen=True)
class RagRunTrace:
    """Safe provenance metadata for one RAG query execution."""

    query_id: str
    timestamp_utc: str
    collection_name: str
    embedding_backend: str
    embedding_model: str
    embedding_alias: str
    embedding_dimensions: int
    retrieval_latency_ms: float
    generation_latency_ms: float
    chunk_count: int
    gateway_alias: str | None = None
    guard_result: dict[str, object] | None = None
    strict_mode: bool = False
    total_latency_ms: float | None = None
    prompt_latency_ms: float | None = None
    context_chunk_count: int | None = None

    def __post_init__(self) -> None:
        _validate_non_empty(self.query_id, "query_id")
        _validate_non_empty(self.timestamp_utc, "timestamp_utc")
        _validate_non_empty(self.collection_name, "collection_name")
        _validate_non_empty(self.embedding_backend, "embedding_backend")
        _validate_non_empty(self.embedding_model, "embedding_model")
        _validate_non_empty(self.embedding_alias, "embedding_alias")
        _validate_positive_int(self.embedding_dimensions, "embedding_dimensions")
        _validate_non_negative_float(
            self.retrieval_latency_ms,
            "retrieval_latency_ms",
        )
        _validate_non_negative_float(
            self.generation_latency_ms,
            "generation_latency_ms",
        )
        _validate_non_negative_int(self.chunk_count, "chunk_count")
        if self.gateway_alias is not None:
            _validate_non_empty(self.gateway_alias, "gateway_alias")
        if self.total_latency_ms is not None:
            _validate_non_negative_float(self.total_latency_ms, "total_latency_ms")
        if self.prompt_latency_ms is not None:
            _validate_non_negative_float(self.prompt_latency_ms, "prompt_latency_ms")
        if self.context_chunk_count is not None:
            _validate_non_negative_int(
                self.context_chunk_count,
                "context_chunk_count",
            )
        if self.guard_result is not None:
            _summarize_guard_result(self.guard_result)

    def to_log_dict(self) -> dict[str, object]:
        """Return safe scalar metadata for structured logging."""
        values: dict[str, object] = {
            "query_id": self.query_id,
            "timestamp_utc": self.timestamp_utc,
            "collection_name": self.collection_name,
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "embedding_alias": self.embedding_alias,
            "embedding_dimensions": self.embedding_dimensions,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
            "chunk_count": self.chunk_count,
            "strict_mode": self.strict_mode,
        }
        if self.gateway_alias is not None:
            values["gateway_alias"] = self.gateway_alias
        if self.guard_result is not None:
            values["guard_result"] = _summarize_guard_result(self.guard_result)
        if self.total_latency_ms is not None:
            values["total_latency_ms"] = self.total_latency_ms
        if self.prompt_latency_ms is not None:
            values["prompt_latency_ms"] = self.prompt_latency_ms
        if self.context_chunk_count is not None:
            values["context_chunk_count"] = self.context_chunk_count
        return values


def build_rag_run_trace(
    *,
    collection_name: str,
    embedding_backend: str,
    embedding_model: str,
    embedding_alias: str,
    embedding_dimensions: int,
    expected_dimensions: int,
    retrieval_latency_ms: float,
    generation_latency_ms: float,
    chunk_count: int,
    query_id: str | None = None,
    timestamp_utc: str | None = None,
    gateway_alias: str | None = None,
    guard_result: Mapping[str, object] | None = None,
    strict_mode: bool = False,
    total_latency_ms: float | None = None,
    prompt_latency_ms: float | None = None,
    context_chunk_count: int | None = None,
) -> RagRunTrace:
    """Build a validated safe RAG provenance trace."""
    if embedding_dimensions != expected_dimensions:
        raise EmbeddingDimensionMismatchError(
            "RAG trace embedding dimensions do not match active configuration."
        )
    return RagRunTrace(
        query_id=query_id or uuid4().hex,
        timestamp_utc=timestamp_utc or _utc_now_iso(),
        collection_name=collection_name,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_alias=embedding_alias,
        embedding_dimensions=embedding_dimensions,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        chunk_count=chunk_count,
        gateway_alias=gateway_alias,
        guard_result=dict(guard_result) if guard_result is not None else None,
        strict_mode=strict_mode,
        total_latency_ms=total_latency_ms,
        prompt_latency_ms=prompt_latency_ms,
        context_chunk_count=context_chunk_count,
    )


def load_rag_tracing_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> RagTracingConfig:
    """Load tracing and active embedding metadata from RAG config."""
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rag_config.yaml must contain a mapping")
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        raise ValueError("rag_config.yaml must contain rag mapping")

    tracing = rag.get("tracing", {})
    if tracing is None:
        tracing = {}
    if not isinstance(tracing, Mapping):
        raise ValueError("rag.tracing must be a mapping")

    qdrant = rag.get("qdrant", {})
    if qdrant is None:
        qdrant = {}
    if not isinstance(qdrant, Mapping):
        raise ValueError("rag.qdrant must be a mapping")

    active = load_active_embedding_metadata(path)
    return RagTracingConfig(
        enabled=_bool_value(tracing, "enabled", True),
        log_level=_string_value(tracing, "log_level", "INFO"),
        collection_name=_string_value(qdrant, "collection", DEFAULT_COLLECTION_NAME),
        embedding_backend=active.backend,
        embedding_model=active.model,
        embedding_alias=active.alias,
        embedding_dimensions=active.dimensions,
    ).validated()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _summarize_guard_result(guard_result: Mapping[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in SAFE_GUARD_RESULT_KEYS:
        value = guard_result.get(key)
        if isinstance(value, bool):
            summary[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            summary[key] = value
    return summary


def _bool_value(data: Mapping[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"rag.tracing.{key} must be boolean")
    return value


def _string_value(data: Mapping[str, object], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"rag.tracing.{key} must be a string")
    return value


def _validate_non_empty(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{field_name} cannot be empty")
    return clean_value


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def _validate_non_negative_float(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    if float(value) < 0.0:
        raise ValueError(f"{field_name} cannot be negative")
