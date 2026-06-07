"""Safe structured logging for retrieval events.

The module builds schema-versioned metadata-only events. It never stores query
text, chunk text, document text, payloads, vectors, embeddings, prompts or
answers in the structured event.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol


RETRIEVAL_LOG_SCHEMA_VERSION = "retrieval-log-v1"
SERVICE_NAME_DEFAULT = "quimera-retrieval"
ENV_DEFAULT = "local"
MAX_TOP_K_SCORES = 10
SCORE_DECIMALS = 6
LATENCY_DECIMALS = 3

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "query",
        "query_text",
        "text",
        "chunk_text",
        "raw_text",
        "content",
        "page_content",
        "document",
        "documents",
        "payload",
        "prompt",
        "answer",
        "completion",
        "response",
        "vector",
        "vectors",
        "dense_vector",
        "sparse_vector",
        "embedding",
        "embeddings",
        "messages",
        "chat_history",
    }
)

RetrievalModeName = Literal["dense_only", "hybrid"]
RetrievalLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
FusionStrategy = Literal["none", "weighted_rrf", "rrf", "dbsf"]

ALLOWED_MODES = frozenset({"dense_only", "hybrid"})
ALLOWED_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
ALLOWED_FUSION_STRATEGIES = frozenset({"none", "weighted_rrf", "rrf", "dbsf"})


@dataclass(frozen=True, slots=True)
class ScoreStats:
    """Aggregated score diagnostics without result IDs or payloads."""

    count: int
    score_min: float
    score_max: float
    score_mean: float
    score_p50: float
    rank1_gap: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "count", _validate_non_negative_int(self.count, "count")
        )
        for field_name in (
            "score_min",
            "score_max",
            "score_mean",
            "score_p50",
            "rank1_gap",
        ):
            object.__setattr__(
                self,
                field_name,
                _round_score(
                    _validate_finite_number(getattr(self, field_name), field_name)
                ),
            )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe score stats."""

        return {
            "count": self.count,
            "score_min": self.score_min,
            "score_max": self.score_max,
            "score_mean": self.score_mean,
            "score_p50": self.score_p50,
            "rank1_gap": self.rank1_gap,
        }


@dataclass(frozen=True, slots=True)
class FusionLogSummary:
    """Small metadata-only summary of the fusion strategy."""

    strategy: str
    profile: str | None = None
    dense_weight: float | None = None
    sparse_weight: float | None = None
    k: float | None = None

    def __post_init__(self) -> None:
        clean_strategy = _validate_optional_text(self.strategy, "strategy")
        if clean_strategy not in ALLOWED_FUSION_STRATEGIES:
            raise ValueError("fusion strategy is not allowed")
        object.__setattr__(self, "strategy", clean_strategy)
        object.__setattr__(
            self,
            "profile",
            None
            if self.profile is None
            else _validate_optional_text(self.profile, "profile"),
        )
        for field_name in ("dense_weight", "sparse_weight", "k"):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None
                if value is None
                else _validate_non_negative_float(value, field_name),
            )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe fusion metadata."""

        return {
            "strategy": self.strategy,
            "profile": self.profile,
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "k": self.k,
        }


@dataclass(frozen=True, slots=True)
class RetrievalEvent:
    """Safe structured retrieval event."""

    schema_version: str
    event_id: str
    level: RetrievalLevel
    mode: RetrievalModeName
    query_hash: str
    query_len: int
    query_is_redacted: bool
    embed_dense_ms: float
    embed_sparse_ms: float
    search_ms: float
    total_ms: float
    chunks_returned: int
    top_k_scores: tuple[float, ...]
    score_stats: ScoreStats
    fusion: FusionLogSummary
    service_name: str = SERVICE_NAME_DEFAULT
    env: str = ENV_DEFAULT
    request_id: str | None = None
    correlation_id: str | None = None
    tenant_id: str | None = None
    otelTraceID: str | None = None
    otelSpanID: str | None = None
    otelServiceName: str | None = None
    otelTraceSampled: bool | None = None

    def __post_init__(self) -> None:
        if self.schema_version != RETRIEVAL_LOG_SCHEMA_VERSION:
            raise ValueError("schema_version must match retrieval log schema")
        object.__setattr__(
            self, "event_id", _validate_optional_text(self.event_id, "event_id")
        )
        object.__setattr__(self, "level", _validate_level(self.level))
        object.__setattr__(self, "mode", _validate_mode(self.mode))
        object.__setattr__(
            self,
            "query_hash",
            _validate_optional_text(self.query_hash, "query_hash"),
        )
        object.__setattr__(
            self,
            "query_len",
            _validate_non_negative_int(self.query_len, "query_len"),
        )
        if self.query_is_redacted is not True:
            raise ValueError("query_is_redacted must be True")
        for field_name in (
            "embed_dense_ms",
            "embed_sparse_ms",
            "search_ms",
            "total_ms",
        ):
            object.__setattr__(self, field_name, safe_ms(getattr(self, field_name)))
        object.__setattr__(
            self,
            "chunks_returned",
            _validate_non_negative_int(self.chunks_returned, "chunks_returned"),
        )
        object.__setattr__(
            self,
            "top_k_scores",
            sanitize_scores(self.top_k_scores),
        )
        object.__setattr__(
            self,
            "service_name",
            _validate_optional_text(self.service_name, "service_name"),
        )
        object.__setattr__(self, "env", _validate_optional_text(self.env, "env"))
        for field_name in (
            "request_id",
            "correlation_id",
            "tenant_id",
            "otelTraceID",
            "otelSpanID",
            "otelServiceName",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                None if value is None else _validate_optional_text(value, field_name),
            )
        if self.otelTraceSampled is not None and not isinstance(
            self.otelTraceSampled, bool
        ):
            raise TypeError("otelTraceSampled must be bool or None")

    def to_dict(self) -> dict[str, object]:
        """Return a flat, Loki/Grafana/OTel-friendly mapping."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "level": self.level,
            "mode": self.mode,
            "query_hash": self.query_hash,
            "query_len": self.query_len,
            "query_is_redacted": self.query_is_redacted,
            "embed_dense_ms": self.embed_dense_ms,
            "embed_sparse_ms": self.embed_sparse_ms,
            "search_ms": self.search_ms,
            "total_ms": self.total_ms,
            "chunks_returned": self.chunks_returned,
            "top_k_scores": list(self.top_k_scores),
            "score_stats": self.score_stats.to_dict(),
            "fusion": self.fusion.to_dict(),
            "service_name": self.service_name,
            "env": self.env,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "otelTraceID": self.otelTraceID,
            "otelSpanID": self.otelSpanID,
            "otelServiceName": self.otelServiceName,
            "otelTraceSampled": self.otelTraceSampled,
        }
        _validate_no_forbidden_keys(payload)
        return payload


class RetrievalLoggerProtocol(Protocol):
    """Logger contract consumed by retrieval code."""

    def log_event(self, event: RetrievalEvent) -> None:
        """Emit one retrieval event."""
        ...


@dataclass(frozen=True, slots=True)
class NullRetrievalLogger:
    """No-op retrieval logger used as the safe default."""

    def log_event(self, event: RetrievalEvent) -> None:
        """Deliberately do nothing."""


@dataclass(slots=True)
class InMemoryRetrievalLogger:
    """Test logger that stores events in memory."""

    events: list[RetrievalEvent] = field(default_factory=list)

    def log_event(self, event: RetrievalEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class PythonLoggingRetrievalLogger:
    """Stdlib logging adapter. It does not configure global logging."""

    logger_name: str = "quimera.rag.retrieval"

    def log_event(self, event: RetrievalEvent) -> None:
        logging.getLogger(self.logger_name).log(
            _level_to_logging(event.level),
            event_to_json(event),
        )


@dataclass(frozen=True, slots=True)
class LoguruRetrievalLogger:
    """Loguru adapter for structured retrieval events."""

    def log_event(self, event: RetrievalEvent) -> None:
        from loguru import logger

        logger.bind(**event_to_log_dict(event)).log(event.level, "retrieval_event")


def compute_score_stats(scores: Sequence[float]) -> ScoreStats:
    """Compute deterministic score stats.

    ``scores`` must be in rank order, best score first. ``rank1_gap`` is
    computed as ``scores[0] - scores[1]``. Passing scores in ascending order
    intentionally produces a negative gap; the logger records that signal
    instead of clamping it.
    """

    clean_scores = tuple(_validate_finite_number(score, "score") for score in scores)
    if not clean_scores:
        return ScoreStats(
            count=0,
            score_min=0.0,
            score_max=0.0,
            score_mean=0.0,
            score_p50=0.0,
            rank1_gap=0.0,
        )
    sorted_scores = sorted(clean_scores)
    rank1_gap = clean_scores[0] - clean_scores[1] if len(clean_scores) >= 2 else 0.0
    return ScoreStats(
        count=len(clean_scores),
        score_min=min(clean_scores),
        score_max=max(clean_scores),
        score_mean=sum(clean_scores) / float(len(clean_scores)),
        score_p50=_p50(sorted_scores),
        rank1_gap=rank1_gap,
    )


def make_query_hash(query: str) -> str:
    """Return a stable short SHA-256 hash for a query without returning text."""

    clean_query = _validate_query(query)
    return hashlib.sha256(clean_query.encode("utf-8")).hexdigest()[:16]


def make_event_id(query_hash: str, mode: str, started_at_ns: int) -> str:
    """Return a deterministic event id."""

    clean_hash = _validate_optional_text(query_hash, "query_hash")
    clean_mode = _validate_mode(mode)
    clean_started = _validate_non_negative_int(started_at_ns, "started_at_ns")
    payload = f"{clean_hash}:{clean_mode}:{clean_started}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def safe_ms(value: float) -> float:
    """Return finite non-negative milliseconds rounded for logs."""

    clean = _validate_finite_number(value, "latency")
    return max(0.0, round(clean, LATENCY_DECIMALS))


def sanitize_scores(
    scores: Sequence[float],
    limit: int = MAX_TOP_K_SCORES,
) -> tuple[float, ...]:
    """Cap and round scores for safe logs."""

    clean_limit = _validate_non_negative_int(limit, "limit")
    return tuple(
        _round_score(_validate_finite_number(score, "score"))
        for score in scores[:clean_limit]
    )


def event_to_log_dict(event: RetrievalEvent) -> dict[str, object]:
    """Return the event as a structured log mapping."""

    return event.to_dict()


def event_to_json(event: RetrievalEvent) -> str:
    """Return the event as deterministic JSON."""

    return json.dumps(event_to_log_dict(event), ensure_ascii=False, sort_keys=True)


def build_retrieval_event(
    *,
    query: str,
    mode: RetrievalModeName,
    embed_dense_ms: float,
    embed_sparse_ms: float,
    search_ms: float,
    total_ms: float,
    top_k_scores: Sequence[float],
    fusion: FusionLogSummary,
    chunks_returned: int,
    level: RetrievalLevel = "INFO",
    started_at_ns: int | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    tenant_id: str | None = None,
    otelTraceID: str | None = None,
    otelSpanID: str | None = None,
    otelServiceName: str | None = None,
    otelTraceSampled: bool | None = None,
) -> RetrievalEvent:
    """Build a safe retrieval event from runtime values."""

    clean_query = _validate_query(query)
    clean_mode = _validate_mode(mode)
    query_hash = make_query_hash(clean_query)
    event_started = (
        time.perf_counter_ns()
        if started_at_ns is None
        else _validate_non_negative_int(started_at_ns, "started_at_ns")
    )
    safe_scores = sanitize_scores(top_k_scores)
    return RetrievalEvent(
        schema_version=RETRIEVAL_LOG_SCHEMA_VERSION,
        event_id=make_event_id(query_hash, clean_mode, event_started),
        level=_validate_level(level),
        mode=clean_mode,
        query_hash=query_hash,
        query_len=len(clean_query),
        query_is_redacted=True,
        embed_dense_ms=embed_dense_ms,
        embed_sparse_ms=embed_sparse_ms,
        search_ms=search_ms,
        total_ms=total_ms,
        chunks_returned=chunks_returned,
        top_k_scores=safe_scores,
        score_stats=compute_score_stats(safe_scores),
        fusion=fusion,
        request_id=request_id,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        otelTraceID=otelTraceID,
        otelSpanID=otelSpanID,
        otelServiceName=otelServiceName,
        otelTraceSampled=otelTraceSampled,
    )


def extract_scores_from_results(results: Sequence[object]) -> tuple[float, ...]:
    """Extract rrf_score or score from result-like objects."""

    extracted: list[float] = []
    for result in results:
        score = _score_from_result(result)
        if score is not None:
            extracted.append(score)
    return sanitize_scores(extracted)


def safe_log_retrieval_event(
    logger: RetrievalLoggerProtocol,
    event: RetrievalEvent,
) -> None:
    """Emit an event, swallowing logger failures so retrieval never fails."""

    try:
        logger.log_event(event)
    except Exception:
        return


def configure_retrieval_log_sink(
    log_dir: Path,
    rotation: str = "10 MB",
    retention: str = "7 days",
    level: str = "INFO",
) -> None:
    """Install an opt-in loguru JSON sink for retrieval events."""

    from loguru import logger

    clean_level = _validate_level(level)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "retrieval.jsonl",
        rotation=rotation,
        retention=retention,
        level=clean_level,
        serialize=True,
        enqueue=True,
        diagnose=False,
        backtrace=False,
        filter=lambda record: (
            "schema_version" in record["extra"] and "event_id" in record["extra"]
        ),
    )


def _score_from_result(result: object) -> float | None:
    if isinstance(result, dict):
        raw = result.get("rrf_score")
        if raw is None:
            raw = result.get("score")
        return None if raw is None else _validate_finite_number(raw, "score")

    raw_attr = getattr(result, "rrf_score", None)
    if raw_attr is None:
        raw_attr = getattr(result, "score", None)
    return None if raw_attr is None else _validate_finite_number(raw_attr, "score")


def _validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if "\x00" in query:
        raise ValueError("query cannot contain null bytes")
    clean = query.strip()
    if not clean:
        raise ValueError("query cannot be empty")
    return clean


def _validate_optional_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain null bytes")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    return clean


def _validate_level(value: str) -> RetrievalLevel:
    clean = _validate_optional_text(value, "level").upper()
    if clean not in ALLOWED_LEVELS:
        raise ValueError("level is not allowed")
    return clean  # type: ignore[return-value]


def _validate_mode(value: str) -> RetrievalModeName:
    clean = _validate_optional_text(value, "mode")
    if clean not in ALLOWED_MODES:
        raise ValueError("mode is not allowed")
    return clean  # type: ignore[return-value]


def _validate_finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    clean = float(value)
    if not math.isfinite(clean):
        raise ValueError(f"{field_name} must be finite")
    return clean


def _validate_non_negative_float(value: float, field_name: str) -> float:
    clean = _validate_finite_number(value, field_name)
    if clean < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return clean


def _validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _round_score(value: float) -> float:
    return round(value, SCORE_DECIMALS)


def _p50(sorted_scores: Sequence[float]) -> float:
    if not sorted_scores:
        return 0.0
    midpoint = len(sorted_scores) // 2
    if len(sorted_scores) % 2 == 1:
        return sorted_scores[midpoint]
    return (sorted_scores[midpoint - 1] + sorted_scores[midpoint]) / 2.0


def _level_to_logging(level: str) -> int:
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }[_validate_level(level)]


def _validate_no_forbidden_keys(payload: dict[str, object]) -> None:
    """Raise ValueError if a forbidden key appears anywhere in a mapping.

    Recurses into nested dictionaries and lists. Current ``to_dict()`` shapes
    are shallow apart from ``score_stats`` and ``fusion``, but the recursive
    check keeps the helper safe if future fields add nested structures.
    """

    for key, value in payload.items():
        if key in FORBIDDEN_LOG_KEYS:
            raise ValueError(f"forbidden log key: {key}")
        if isinstance(value, dict):
            _validate_no_forbidden_keys(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _validate_no_forbidden_keys(item)


__all__ = [
    "RETRIEVAL_LOG_SCHEMA_VERSION",
    "SERVICE_NAME_DEFAULT",
    "ENV_DEFAULT",
    "MAX_TOP_K_SCORES",
    "SCORE_DECIMALS",
    "LATENCY_DECIMALS",
    "FORBIDDEN_LOG_KEYS",
    "RetrievalModeName",
    "RetrievalLevel",
    "FusionStrategy",
    "ScoreStats",
    "FusionLogSummary",
    "RetrievalEvent",
    "RetrievalLoggerProtocol",
    "NullRetrievalLogger",
    "InMemoryRetrievalLogger",
    "PythonLoggingRetrievalLogger",
    "LoguruRetrievalLogger",
    "compute_score_stats",
    "make_query_hash",
    "make_event_id",
    "safe_ms",
    "sanitize_scores",
    "event_to_log_dict",
    "event_to_json",
    "build_retrieval_event",
    "extract_scores_from_results",
    "safe_log_retrieval_event",
    "configure_retrieval_log_sink",
]
