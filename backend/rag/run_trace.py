"""Safe per-query provenance trace for local RAG runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
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
RUN_CONTEXTS = frozenset({"cold_start", "warm_model", "degraded_qdrant"})

RagRunContext = Literal["cold_start", "warm_model", "degraded_qdrant"]


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
    routing_ms: float | None = None
    embedding_ms: float | None = None
    retrieval_ms: float | None = None
    context_pack_ms: float | None = None
    prompt_build_ms: float | None = None
    generation_ms: float | None = None
    total_ms: float | None = None
    run_context: RagRunContext | None = None
    ollama_metrics_available: bool = False
    ollama_total_duration_ms: float | None = None
    ollama_load_duration_ms: float | None = None
    ollama_prompt_eval_count: int | None = None
    ollama_prompt_eval_duration_ms: float | None = None
    ollama_eval_count: int | None = None
    ollama_eval_duration_ms: float | None = None

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
        for field_name in (
            "routing_ms",
            "embedding_ms",
            "retrieval_ms",
            "context_pack_ms",
            "prompt_build_ms",
            "generation_ms",
            "total_ms",
            "ollama_total_duration_ms",
            "ollama_load_duration_ms",
            "ollama_prompt_eval_duration_ms",
            "ollama_eval_duration_ms",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _validate_non_negative_float(value, field_name)
        for field_name in (
            "ollama_prompt_eval_count",
            "ollama_eval_count",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _validate_non_negative_int(value, field_name)
        if self.run_context is not None and self.run_context not in RUN_CONTEXTS:
            raise ValueError(
                f"run_context must be one of {sorted(RUN_CONTEXTS)}"
            )
        if self.ollama_metrics_available and not any(
            value is not None
            for value in (
                self.ollama_total_duration_ms,
                self.ollama_load_duration_ms,
                self.ollama_prompt_eval_count,
                self.ollama_prompt_eval_duration_ms,
                self.ollama_eval_count,
                self.ollama_eval_duration_ms,
            )
        ):
            raise ValueError(
                "ollama_metrics_available cannot be true without metric fields"
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
        optional_segment_values: dict[str, object | None] = {
            "routing_ms": self.routing_ms,
            "embedding_ms": self.embedding_ms,
            "retrieval_ms": self.retrieval_ms,
            "context_pack_ms": self.context_pack_ms,
            "prompt_build_ms": self.prompt_build_ms,
            "generation_ms": self.generation_ms,
            "total_ms": self.total_ms,
            "run_context": self.run_context,
            "ollama_total_duration_ms": self.ollama_total_duration_ms,
            "ollama_load_duration_ms": self.ollama_load_duration_ms,
            "ollama_prompt_eval_count": self.ollama_prompt_eval_count,
            "ollama_prompt_eval_duration_ms": self.ollama_prompt_eval_duration_ms,
            "ollama_eval_count": self.ollama_eval_count,
            "ollama_eval_duration_ms": self.ollama_eval_duration_ms,
        }
        values["ollama_metrics_available"] = self.ollama_metrics_available
        for key, value in optional_segment_values.items():
            if value is not None:
                values[key] = value
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
    routing_ms: float | None = None,
    embedding_ms: float | None = None,
    retrieval_ms: float | None = None,
    context_pack_ms: float | None = None,
    prompt_build_ms: float | None = None,
    generation_ms: float | None = None,
    total_ms: float | None = None,
    run_context: RagRunContext | None = None,
    ollama_metrics: Mapping[str, object] | None = None,
) -> RagRunTrace:
    """Build a validated safe RAG provenance trace."""
    if embedding_dimensions != expected_dimensions:
        raise EmbeddingDimensionMismatchError(
            "RAG trace embedding dimensions do not match active configuration."
        )
    safe_ollama_metrics = extract_ollama_metrics(ollama_metrics)
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
        routing_ms=routing_ms,
        embedding_ms=embedding_ms,
        retrieval_ms=retrieval_ms,
        context_pack_ms=context_pack_ms,
        prompt_build_ms=prompt_build_ms,
        generation_ms=generation_ms,
        total_ms=total_ms,
        run_context=run_context,
        ollama_metrics_available=bool(
            safe_ollama_metrics["ollama_metrics_available"]
        ),
        ollama_total_duration_ms=_optional_float_metric(
            safe_ollama_metrics,
            "ollama_total_duration_ms",
        ),
        ollama_load_duration_ms=_optional_float_metric(
            safe_ollama_metrics,
            "ollama_load_duration_ms",
        ),
        ollama_prompt_eval_count=_optional_int_metric(
            safe_ollama_metrics,
            "ollama_prompt_eval_count",
        ),
        ollama_prompt_eval_duration_ms=_optional_float_metric(
            safe_ollama_metrics,
            "ollama_prompt_eval_duration_ms",
        ),
        ollama_eval_count=_optional_int_metric(
            safe_ollama_metrics,
            "ollama_eval_count",
        ),
        ollama_eval_duration_ms=_optional_float_metric(
            safe_ollama_metrics,
            "ollama_eval_duration_ms",
        ),
    )


def extract_ollama_metrics(metadata: Mapping[str, object] | None) -> dict[str, object]:
    """Extract safe Ollama timing/count metrics from already available metadata.

    Durations from Ollama are nanoseconds; trace fields store milliseconds.
    The function never calls Ollama and never inspects prompt or answer text.
    """
    if metadata is None:
        return {"ollama_metrics_available": False}
    metrics: dict[str, object] = {}
    duration_fields = {
        "total_duration": "ollama_total_duration_ms",
        "load_duration": "ollama_load_duration_ms",
        "prompt_eval_duration": "ollama_prompt_eval_duration_ms",
        "eval_duration": "ollama_eval_duration_ms",
    }
    count_fields = {
        "prompt_eval_count": "ollama_prompt_eval_count",
        "eval_count": "ollama_eval_count",
    }
    for source_key, target_key in duration_fields.items():
        value = metadata.get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[target_key] = float(value) / 1_000_000.0
    for source_key, target_key in count_fields.items():
        value = metadata.get(source_key)
        if isinstance(value, int) and not isinstance(value, bool):
            metrics[target_key] = value
    metrics["ollama_metrics_available"] = bool(metrics)
    return metrics


def _optional_float_metric(
    metrics: Mapping[str, object],
    key: str,
) -> float | None:
    value = metrics.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_int_metric(metrics: Mapping[str, object], key: str) -> int | None:
    value = metrics.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


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
