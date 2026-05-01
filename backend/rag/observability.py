"""Safe local RAG lifecycle observability events.

These events are local loguru structured logs only.  They deliberately carry
metadata about the lifecycle stage, never user text, chunks, prompts, answers,
vectors, payloads, or secrets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import httpx
import yaml
from loguru import logger

from backend.rag.collection_guard import EmbeddingDimensionMismatchError


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_CONFIG_PATH = REPO_ROOT / "config" / "rag_config.yaml"
ALLOWED_OBSERVABILITY_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING"})
FORBIDDEN_OBSERVABILITY_KEYS = frozenset(
    {
        "query",
        "question",
        "prompt",
        "answer",
        "response",
        "chunk",
        "chunk_text",
        "chunks",
        "document",
        "documents",
        "vector",
        "vectors",
        "embedding",
        "embedding_values",
        "payload",
        "qdrant_payload",
        "portfolio",
        "carteira",
        "api_key",
        "authorization",
        "secret",
        "token",
        "password",
        "headers",
    }
)


class RagEventKind(str, Enum):
    """Safe RAG lifecycle event names."""

    EMBEDDING_CALL_STARTED = "embedding_call_started"
    EMBEDDING_CALL_FINISHED = "embedding_call_finished"
    EMBEDDING_CALL_FAILED = "embedding_call_failed"
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_FINISHED = "retrieval_finished"
    RETRIEVAL_FAILED = "retrieval_failed"
    GENERATION_STARTED = "generation_started"
    GENERATION_FINISHED = "generation_finished"
    GENERATION_FAILED = "generation_failed"
    COLLECTION_GUARD_WARNING = "collection_guard_warning"
    COLLECTION_GUARD_ERROR = "collection_guard_error"


class RagErrorCategory(str, Enum):
    """Coarse, safe error categories for lifecycle events."""

    TIMEOUT = "timeout"
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    INVALID_RESPONSE = "invalid_response"
    DIMENSION_MISMATCH = "dimension_mismatch"
    HTTP_ERROR = "http_error"
    BACKEND_UNREACHABLE = "backend_unreachable"
    EMPTY_RESULT = "empty_result"
    COLLECTION_GUARD_STRICT = "collection_guard_strict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RagObservabilityConfig:
    """Configuration for local RAG lifecycle event emission."""

    enabled: bool = True
    log_level: str = "INFO"
    embedding_events_enabled: bool = True
    retrieval_events_enabled: bool = True
    generation_events_enabled: bool = True
    collection_guard_events_enabled: bool = True

    def validated(self) -> RagObservabilityConfig:
        """Return a validated copy of this config."""
        level = self.log_level.strip().upper()
        if level not in ALLOWED_OBSERVABILITY_LOG_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_OBSERVABILITY_LOG_LEVELS))
            raise ValueError(f"rag.observability.log_level must be one of: {allowed}")
        return RagObservabilityConfig(
            enabled=self.enabled,
            log_level=level,
            embedding_events_enabled=self.embedding_events_enabled,
            retrieval_events_enabled=self.retrieval_events_enabled,
            generation_events_enabled=self.generation_events_enabled,
            collection_guard_events_enabled=self.collection_guard_events_enabled,
        )


@dataclass(frozen=True)
class RagObservabilityEvent:
    """Safe metadata-only RAG lifecycle event."""

    event_kind: RagEventKind
    timestamp_utc: str
    backend: str
    alias: str
    model: str | None = None
    dimensions: int | None = None
    latency_ms: float | None = None
    chunk_count: int | None = None
    batch_size: int | None = None
    status: str | None = None
    error_category: RagErrorCategory | None = None
    collection_name: str | None = None
    query_id: str | None = None
    gateway_alias: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty(self.timestamp_utc, "timestamp_utc")
        _validate_non_empty(self.backend, "backend")
        _validate_non_empty(self.alias, "alias")
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        if self.chunk_count is not None and self.chunk_count < 0:
            raise ValueError("chunk_count cannot be negative")
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

    def to_log_dict(self) -> dict[str, object]:
        """Return allowlisted safe scalar metadata for loguru binding."""
        data: dict[str, object] = {
            "event_kind": self.event_kind.value,
            "timestamp_utc": self.timestamp_utc,
            "backend": self.backend,
            "alias": self.alias,
        }
        optional_values: Mapping[str, object | None] = {
            "model": self.model,
            "dimensions": self.dimensions,
            "latency_ms": self.latency_ms,
            "chunk_count": self.chunk_count,
            "batch_size": self.batch_size,
            "status": self.status,
            "error_category": (
                self.error_category.value if self.error_category is not None else None
            ),
            "collection_name": self.collection_name,
            "query_id": self.query_id,
            "gateway_alias": self.gateway_alias,
        }
        for key, value in optional_values.items():
            if value is not None:
                data[key] = value
        return data


def load_rag_observability_config(
    config_path: str | Path = DEFAULT_RAG_CONFIG_PATH,
) -> RagObservabilityConfig:
    """Load RAG observability config from ``config/rag_config.yaml``."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        return RagObservabilityConfig().validated()
    rag = raw.get("rag")
    if not isinstance(rag, Mapping):
        return RagObservabilityConfig().validated()
    observability = rag.get("observability")
    if not isinstance(observability, Mapping):
        return RagObservabilityConfig().validated()

    return RagObservabilityConfig(
        enabled=_bool_from_mapping(observability, "enabled", True),
        log_level=str(observability.get("log_level", "INFO")),
        embedding_events_enabled=_bool_from_mapping(
            observability,
            "embedding_events_enabled",
            True,
        ),
        retrieval_events_enabled=_bool_from_mapping(
            observability,
            "retrieval_events_enabled",
            True,
        ),
        generation_events_enabled=_bool_from_mapping(
            observability,
            "generation_events_enabled",
            True,
        ),
        collection_guard_events_enabled=_bool_from_mapping(
            observability,
            "collection_guard_events_enabled",
            True,
        ),
    ).validated()


def emit_rag_event(
    event: RagObservabilityEvent,
    config: RagObservabilityConfig,
) -> None:
    """Emit a local structured RAG lifecycle event if enabled."""
    safe_config = config.validated()
    if not safe_config.enabled:
        return
    logger.bind(event=event.to_log_dict()).log(
        safe_config.log_level,
        "rag_lifecycle_event",
    )


def categorize_exception(exc: Exception) -> RagErrorCategory:
    """Map known local exceptions to safe categories without messages."""
    exc_name = exc.__class__.__name__
    if isinstance(exc, httpx.TimeoutException) or exc_name == "GatewayTimeoutError":
        return RagErrorCategory.TIMEOUT
    if isinstance(exc, httpx.ConnectError) or exc_name == "GatewayConnectionError":
        return RagErrorCategory.CONNECTION
    if exc_name == "GatewayAuthenticationError":
        return RagErrorCategory.AUTHENTICATION
    if (
        isinstance(exc, ValueError)
        or exc_name == "GatewayResponseError"
        or exc_name == "EmbeddingError"
    ):
        return RagErrorCategory.INVALID_RESPONSE
    if isinstance(exc, EmbeddingDimensionMismatchError):
        return RagErrorCategory.DIMENSION_MISMATCH
    if isinstance(exc, httpx.HTTPStatusError):
        return RagErrorCategory.HTTP_ERROR
    if isinstance(exc, httpx.TransportError):
        return RagErrorCategory.BACKEND_UNREACHABLE
    return RagErrorCategory.UNKNOWN


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with a compact Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _bool_from_mapping(
    values: Mapping[object, object],
    key: str,
    default: bool,
) -> bool:
    raw = values.get(key, default)
    if not isinstance(raw, bool):
        raise ValueError(f"rag.observability.{key} must be a boolean")
    return raw


def _validate_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
