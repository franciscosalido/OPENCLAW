"""Immutable value models for hot working memory."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from backend.working_memory.safety import (
    compute_payload_checksum,
    sanitize_metadata,
    validate_safe_payload,
    validate_safe_summary,
)


SCHEMA_VERSION_POINT_V1 = "working-memory-point-v1"
MemoryKind = Literal["turn_summary", "agent_state", "scratchpad", "handoff", "tool_observation"]


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkingMemoryPoint:
    """A single hot working-memory point.

    The vector is intentionally excluded from repr and from Qdrant payload.
    """

    point_id: str
    agent_id: str
    session_id: UUID
    memory_kind: MemoryKind
    vector: tuple[float, ...] = field(repr=False)
    vector_dim: int
    recency_ts: datetime
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    ttl_seconds: int
    embedding_model: str
    source_ref: str | None = None
    topic: str | None = None
    task_id: str | None = None
    importance: float = 0.5
    checkpoint_id: str | None = None
    safe_summary: str | None = field(default=None, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    schema_version: str = SCHEMA_VERSION_POINT_V1

    def __post_init__(self) -> None:
        _require_non_empty(self.point_id, "point_id")
        _require_non_empty(self.agent_id, "agent_id")
        _require_non_empty(self.embedding_model, "embedding_model")
        if not isinstance(self.session_id, UUID):
            raise TypeError("session_id must be a UUID")
        if self.memory_kind not in ("turn_summary", "agent_state", "scratchpad", "handoff", "tool_observation"):
            raise ValueError("memory_kind is unsupported")
        _validate_vector(self.vector)
        if self.vector_dim != len(self.vector):
            raise ValueError("vector_dim must match vector length")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0.0 and 1.0")
        for field_name in ("recency_ts", "created_at", "updated_at", "expires_at"):
            _require_tzaware(getattr(self, field_name), field_name)
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be greater than created_at")
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if self.schema_version != SCHEMA_VERSION_POINT_V1:
            raise ValueError("schema_version must be working-memory-point-v1")
        object.__setattr__(self, "safe_summary", validate_safe_summary(self.safe_summary))
        object.__setattr__(self, "metadata", sanitize_metadata(validate_safe_payload(self.metadata)))

    @property
    def payload_checksum(self) -> str:
        """Return checksum over the safe payload, excluding the checksum itself."""

        return compute_payload_checksum(self._payload_without_checksum())

    def is_expired(self, now: datetime | None = None) -> bool:
        resolved = now or datetime.now(UTC)
        _require_tzaware(resolved, "now")
        return self.expires_at <= resolved

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Return safe Qdrant payload with no vector or raw content."""

        payload = self._payload_without_checksum()
        payload["payload_checksum"] = self.payload_checksum
        return payload

    def _payload_without_checksum(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "session_id": str(self.session_id),
            "task_id": self.task_id,
            "topic": self.topic,
            "memory_kind": self.memory_kind,
            "source_ref": self.source_ref,
            "importance": self.importance,
            "recency_ts": self.recency_ts.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "embedding_model": self.embedding_model,
            "vector_dim": self.vector_dim,
            "checkpoint_id": self.checkpoint_id,
            "safe_summary": self.safe_summary,
            "metadata": self.metadata,
        }


def point_from_payload(*, point_id: str, vector: tuple[float, ...], payload: dict[str, Any]) -> WorkingMemoryPoint:
    """Build a point from a Qdrant/Postgres payload."""

    return WorkingMemoryPoint(
        point_id=point_id,
        agent_id=str(payload["agent_id"]),
        session_id=UUID(str(payload["session_id"])),
        memory_kind=str(payload["memory_kind"]),  # type: ignore[arg-type]
        vector=vector,
        vector_dim=int(payload["vector_dim"]),
        recency_ts=_parse_datetime(payload["recency_ts"]),
        created_at=_parse_datetime(payload["created_at"]),
        updated_at=_parse_datetime(payload.get("updated_at", payload["created_at"])),
        expires_at=_parse_datetime(payload["expires_at"]),
        ttl_seconds=int(payload["ttl_seconds"]),
        embedding_model=str(payload["embedding_model"]),
        source_ref=_optional_str(payload.get("source_ref")),
        topic=_optional_str(payload.get("topic")),
        task_id=_optional_str(payload.get("task_id")),
        importance=float(payload.get("importance", 0.5)),
        checkpoint_id=_optional_str(payload.get("checkpoint_id")),
        safe_summary=_optional_str(payload.get("safe_summary")),
        metadata=dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), dict) else {},
    )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    _require_tzaware(parsed, "datetime")
    return parsed


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_tzaware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validate_vector(vector: tuple[float, ...]) -> None:
    if not vector:
        raise ValueError("vector cannot be empty")
    for item in vector:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError("vector must contain numeric values")
        if not math.isfinite(float(item)):
            raise ValueError("vector must contain finite values")
