"""Domain models for Quimera PostgreSQL temporal memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


TurnRole = Literal["user", "assistant", "system", "tool"]
VALID_TURN_ROLES: frozenset[str] = frozenset(("user", "assistant", "system", "tool"))


@dataclass(frozen=True, slots=True)
class Session:
    """One persisted agent session."""

    session_id: UUID
    agent_id: str
    user_id: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _require_uuid(self.session_id, "session_id")
        _require_non_empty(self.agent_id, "agent_id")
        if self.user_id is not None:
            _require_non_empty(self.user_id, "user_id")
        _require_aware_datetime(self.created_at, "created_at")
        _require_aware_datetime(self.updated_at, "updated_at")
        _require_dict(self.metadata, "metadata")


@dataclass(frozen=True, slots=True)
class Turn:
    """One conversational turn stored inside a session."""

    turn_id: UUID
    session_id: UUID
    role: TurnRole
    content: str
    created_at: datetime
    token_count: int | None
    latency_ms: float | None

    def __post_init__(self) -> None:
        _require_uuid(self.turn_id, "turn_id")
        _require_uuid(self.session_id, "session_id")
        if self.role not in VALID_TURN_ROLES:
            raise ValueError("role must be one of user, assistant, system, tool")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        _require_aware_datetime(self.created_at, "created_at")
        if self.token_count is not None and self.token_count < 0:
            raise ValueError("token_count must be >= 0")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")


@dataclass(frozen=True, slots=True)
class AgentState:
    """JSONB state for one agent key in one session."""

    state_id: UUID
    agent_id: str
    session_id: UUID
    state_key: str
    state_value: dict[str, Any]
    schema_version: str
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_uuid(self.state_id, "state_id")
        _require_uuid(self.session_id, "session_id")
        _require_non_empty(self.agent_id, "agent_id")
        _require_non_empty(self.state_key, "state_key")
        _require_dict(self.state_value, "state_value")
        _require_non_empty(self.schema_version, "schema_version")
        _require_aware_datetime(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class EntityMention:
    """Lightweight entity mention anchored to one turn."""

    mention_id: UUID
    turn_id: UUID
    entity_text: str
    entity_type: str
    start_char: int
    end_char: int
    confidence: float | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.mention_id, "mention_id")
        _require_uuid(self.turn_id, "turn_id")
        _require_non_empty(self.entity_text, "entity_text")
        _require_non_empty(self.entity_type, "entity_type")
        if self.start_char < 0:
            raise ValueError("start_char must be >= 0")
        if self.end_char < self.start_char:
            raise ValueError("end_char must be >= start_char")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


def _require_uuid(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_dict(value: dict[str, Any], field_name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
