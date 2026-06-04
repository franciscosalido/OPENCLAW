"""Async repository for Quimera PostgreSQL temporal memory."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from backend.observability.decorators import traced_pg
from backend.memory.postgres.models import (
    AgentState,
    EntityMention,
    Session,
    Turn,
    TurnRole,
    VALID_TURN_ROLES,
)


class PostgresMemoryRepository:
    """Repository using an injected asyncpg pool wrapper."""

    def __init__(self, client: object) -> None:
        self._pool = cast(asyncpg.Pool, getattr(client, "pool", client))

    async def create_session(
        self,
        agent_id: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        row = await self._pool.fetchrow(
            """
            INSERT INTO sessions(agent_id, user_id, metadata)
            VALUES($1, $2, $3)
            RETURNING *
            """,
            agent_id,
            user_id,
            metadata or {},
        )
        return _session_from_record(_require_row(row))

    async def get_session(self, session_id: object) -> Session | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM sessions WHERE session_id = $1",
            _as_uuid(session_id, "session_id"),
        )
        return None if row is None else _session_from_record(row)

    @traced_pg(table="turns", operation="write")
    async def append_turn(
        self,
        session_id: object,
        role: str,
        content: str,
        token_count: int | None = None,
        latency_ms: float | None = None,
    ) -> Turn:
        if role not in VALID_TURN_ROLES:
            raise ValueError("role must be one of user, assistant, system, tool")
        row = await self._pool.fetchrow(
            """
            INSERT INTO turns(session_id, role, content, token_count, latency_ms)
            VALUES($1, $2, $3, $4, $5)
            RETURNING *
            """,
            _as_uuid(session_id, "session_id"),
            role,
            content,
            token_count,
            latency_ms,
        )
        return _turn_from_record(_require_row(row))

    @traced_pg(table="turns", operation="read")
    async def get_recent_turns(self, session_id: object, limit: int = 20) -> list[Turn]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        rows = await self._pool.fetch(
            """
            SELECT *
            FROM (
                SELECT *
                FROM turns
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ) recent
            ORDER BY created_at ASC
            """,
            _as_uuid(session_id, "session_id"),
            limit,
        )
        return [_turn_from_record(row) for row in rows]

    @traced_pg(table="agent_states", operation="write")
    async def upsert_agent_state(
        self,
        agent_id: str,
        session_id: object,
        state_key: str,
        state_value: dict[str, Any],
        schema_version: str = "agent-state-v1",
    ) -> AgentState:
        row = await self._pool.fetchrow(
            """
            INSERT INTO agent_states(
                agent_id,
                session_id,
                state_key,
                state_value,
                schema_version,
                updated_at
            )
            VALUES($1, $2, $3, $4, $5, NOW())
            ON CONFLICT(agent_id, session_id, state_key)
            DO UPDATE SET
                state_value = EXCLUDED.state_value,
                schema_version = EXCLUDED.schema_version,
                updated_at = NOW()
            RETURNING *
            """,
            agent_id,
            _as_uuid(session_id, "session_id"),
            state_key,
            state_value,
            schema_version,
        )
        return _agent_state_from_record(_require_row(row))

    async def get_agent_state(
        self,
        agent_id: str,
        session_id: object,
        state_key: str,
    ) -> AgentState | None:
        row = await self._pool.fetchrow(
            """
            SELECT *
            FROM agent_states
            WHERE agent_id = $1 AND session_id = $2 AND state_key = $3
            """,
            agent_id,
            _as_uuid(session_id, "session_id"),
            state_key,
        )
        return None if row is None else _agent_state_from_record(row)

    async def record_entity_mention(
        self,
        turn_id: object,
        entity_text: str,
        entity_type: str,
        start_char: int,
        end_char: int,
        confidence: float | None = None,
    ) -> EntityMention:
        row = await self._pool.fetchrow(
            """
            INSERT INTO entity_mentions(
                turn_id,
                entity_text,
                entity_type,
                start_char,
                end_char,
                confidence
            )
            VALUES($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            _as_uuid(turn_id, "turn_id"),
            entity_text,
            entity_type,
            start_char,
            end_char,
            confidence,
        )
        return _entity_mention_from_record(_require_row(row))

    async def get_entity_mentions_for_turn(self, turn_id: object) -> list[EntityMention]:
        rows = await self._pool.fetch(
            """
            SELECT *
            FROM entity_mentions
            WHERE turn_id = $1
            ORDER BY start_char ASC, end_char ASC
            """,
            _as_uuid(turn_id, "turn_id"),
        )
        return [_entity_mention_from_record(row) for row in rows]


def _require_row(row: asyncpg.Record | None) -> asyncpg.Record:
    if row is None:
        raise RuntimeError("database write returned no row")
    return row


def _as_uuid(value: object, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError(f"{field_name} must be a UUID or UUID string")


def _session_from_record(row: asyncpg.Record) -> Session:
    return Session(
        session_id=row["session_id"],
        agent_id=row["agent_id"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=dict(row["metadata"]),
    )


def _turn_from_record(row: asyncpg.Record) -> Turn:
    return Turn(
        turn_id=row["turn_id"],
        session_id=row["session_id"],
        role=cast(TurnRole, row["role"]),
        content=row["content"],
        created_at=row["created_at"],
        token_count=row["token_count"],
        latency_ms=row["latency_ms"],
    )


def _agent_state_from_record(row: asyncpg.Record) -> AgentState:
    return AgentState(
        state_id=row["state_id"],
        agent_id=row["agent_id"],
        session_id=row["session_id"],
        state_key=row["state_key"],
        state_value=dict(row["state_value"]),
        schema_version=row["schema_version"],
        updated_at=row["updated_at"],
    )


def _entity_mention_from_record(row: asyncpg.Record) -> EntityMention:
    return EntityMention(
        mention_id=row["mention_id"],
        turn_id=row["turn_id"],
        entity_text=row["entity_text"],
        entity_type=row["entity_type"],
        start_char=row["start_char"],
        end_char=row["end_char"],
        confidence=row["confidence"],
    )
