"""Asyncpg client for Quimera PostgreSQL memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from backend.memory.postgres.models import AgentState, EntityMention, Session, Turn
from backend.memory.postgres.settings import PostgresSettings


@dataclass(frozen=True, slots=True)
class PostgresClient:
    """Small asyncpg pool wrapper with JSONB codecs and healthcheck."""

    pool: asyncpg.Pool

    @classmethod
    async def create(
        cls,
        settings: PostgresSettings | str | None = None,
        *,
        dsn: str | None = None,
    ) -> "PostgresClient":
        """Create a pool from settings or explicit DSN."""

        resolved = _resolve_settings(settings=settings, dsn=dsn)
        pool = await asyncpg.create_pool(
            dsn=resolved.dsn,
            min_size=resolved.min_pool_size,
            max_size=resolved.max_pool_size,
            command_timeout=resolved.command_timeout,
            init=_configure_json_codecs,
        )
        return cls(pool=pool)

    async def close(self) -> None:
        """Close the underlying pool."""

        await self.pool.close()

    async def healthcheck(self) -> bool:
        """Return whether `SELECT 1` succeeds."""

        value = await self.pool.fetchval("SELECT 1")
        return bool(value == 1)

    async def create_session(
        self,
        agent_id: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        from backend.memory.postgres.repository import PostgresMemoryRepository

        return await PostgresMemoryRepository(self).create_session(
            agent_id,
            user_id=user_id,
            metadata=metadata,
        )

    async def get_session(self, session_id: object) -> Session | None:
        from backend.memory.postgres.repository import PostgresMemoryRepository

        return await PostgresMemoryRepository(self).get_session(session_id)

    async def append_turn(
        self,
        session_id: object,
        role: str,
        content: str,
        token_count: int | None = None,
        latency_ms: float | None = None,
    ) -> Turn:
        from backend.memory.postgres.repository import PostgresMemoryRepository

        return await PostgresMemoryRepository(self).append_turn(
            session_id,
            role,
            content,
            token_count=token_count,
            latency_ms=latency_ms,
        )

    async def upsert_agent_state(
        self,
        agent_id: str,
        session_id: object,
        state_key: str,
        state_value: dict[str, Any],
        schema_version: str = "agent-state-v1",
    ) -> AgentState:
        from backend.memory.postgres.repository import PostgresMemoryRepository

        return await PostgresMemoryRepository(self).upsert_agent_state(
            agent_id,
            session_id,
            state_key,
            state_value,
            schema_version=schema_version,
        )

    async def record_entity_mention(
        self,
        turn_id: object,
        entity_text: str,
        entity_type: str,
        start_char: int,
        end_char: int,
        confidence: float | None = None,
    ) -> EntityMention:
        from backend.memory.postgres.repository import PostgresMemoryRepository

        return await PostgresMemoryRepository(self).record_entity_mention(
            turn_id,
            entity_text,
            entity_type,
            start_char,
            end_char,
            confidence=confidence,
        )


async def _configure_json_codecs(connection: asyncpg.Connection) -> None:
    for type_name in ("json", "jsonb"):
        await connection.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
            format="text",
        )


def _resolve_settings(
    *,
    settings: PostgresSettings | str | None,
    dsn: str | None,
) -> PostgresSettings:
    if dsn is not None:
        base = PostgresSettings()
        return PostgresSettings(
            dsn=dsn,
            min_pool_size=base.min_pool_size,
            max_pool_size=base.max_pool_size,
            command_timeout=base.command_timeout,
        )
    if isinstance(settings, PostgresSettings):
        return settings
    if isinstance(settings, str):
        base = PostgresSettings()
        return PostgresSettings(
            dsn=settings,
            min_pool_size=base.min_pool_size,
            max_pool_size=base.max_pool_size,
            command_timeout=base.command_timeout,
        )
    return PostgresSettings()
