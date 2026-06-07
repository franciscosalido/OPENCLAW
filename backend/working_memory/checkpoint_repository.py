"""Asyncpg repository for pgvector working-memory checkpoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from backend.observability.decorators import traced_pg
from backend.working_memory.models import WorkingMemoryPoint
from backend.working_memory.safety import compute_payload_checksum, sanitize_metadata


class PoolLike(Protocol):
    async def fetchrow(self, query: str, *args: object) -> Any: ...
    async def fetch(self, query: str, *args: object) -> list[Any]: ...
    async def execute(self, query: str, *args: object) -> str: ...


class WorkingMemoryCheckpointRepository:
    """Persist and load working-memory checkpoints through asyncpg."""

    def __init__(self, pool: asyncpg.Pool | PoolLike) -> None:
        self._pool = pool

    @traced_pg("working_memory_snapshots", "INSERT")
    async def create_snapshot_header(
        self,
        *,
        agent_id: str,
        session_id: str,
        snapshot_epoch: int | None,
        collection_name: str,
        vector_name: str,
        embedding_model: str,
        vector_dim: int,
        snapshot_kind: str,
        point_count: int,
        checksum: str,
        expires_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        row = await self._pool.fetchrow(
            """
            WITH locked AS (
                SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2::text))
            ),
            next_epoch AS (
                SELECT COALESCE($3::bigint, COALESCE(MAX(snapshot_epoch), 0) + 1) AS snapshot_epoch
                FROM working_memory_snapshots, locked
                WHERE agent_id = $1 AND session_id = $2
            )
            INSERT INTO working_memory_snapshots (
                agent_id, session_id, snapshot_epoch, collection_name, vector_name,
                embedding_model, vector_dim, snapshot_kind, point_count, checksum,
                expires_at, metadata
            )
            VALUES ($1, $2, (SELECT snapshot_epoch FROM next_epoch), $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING snapshot_id
            """,
            agent_id,
            UUID(session_id),
            snapshot_epoch,
            collection_name,
            vector_name,
            embedding_model,
            vector_dim,
            snapshot_kind,
            point_count,
            checksum,
            expires_at,
            sanitize_metadata(metadata),
        )
        return str(row["snapshot_id"])

    @traced_pg("working_memory_snapshot_points", "INSERT")
    async def insert_snapshot_points(self, *, snapshot_id: str, points: Sequence[WorkingMemoryPoint]) -> None:
        for point in points:
            await self._pool.execute(
                """
                INSERT INTO working_memory_snapshot_points (
                    snapshot_id, point_id, agent_id, session_id, memory_kind,
                    source_ref, topic, safe_summary, embedding_model, vector_dim,
                    memory_vector, importance, recency_ts, expires_at,
                    payload_checksum, metadata, created_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11::vector, $12, $13, $14,
                    $15, $16, $17
                )
                ON CONFLICT (snapshot_id, point_id) DO UPDATE SET
                    payload_checksum = EXCLUDED.payload_checksum,
                    metadata = EXCLUDED.metadata
                """,
                UUID(snapshot_id),
                point.point_id,
                point.agent_id,
                point.session_id,
                point.memory_kind,
                point.source_ref,
                point.topic,
                point.safe_summary,
                point.embedding_model,
                point.vector_dim,
                _vector_literal(point.vector),
                point.importance,
                point.recency_ts,
                point.expires_at,
                point.payload_checksum,
                point.metadata,
                point.created_at,
            )

    async def get_latest_snapshot(self, *, agent_id: str, session_id: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            """
            SELECT *
            FROM working_memory_snapshots
            WHERE agent_id = $1 AND session_id = $2
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY snapshot_epoch DESC, created_at DESC
            LIMIT 1
            """,
            agent_id,
            UUID(session_id),
        )
        return dict(row) if row is not None else None

    async def load_snapshot_points(self, snapshot_id: str) -> list[WorkingMemoryPoint]:
        rows = await self._pool.fetch(
            """
            SELECT *
            FROM working_memory_snapshot_points
            WHERE snapshot_id = $1
            ORDER BY created_at ASC, point_id ASC
            """,
            UUID(snapshot_id),
        )
        return [_point_from_row(dict(row)) for row in rows]

    async def mark_snapshot_restored(self, snapshot_id: str) -> None:
        await self._pool.execute(
            """
            UPDATE working_memory_snapshots
            SET metadata = metadata || '{"restored": true}'::jsonb
            WHERE snapshot_id = $1
            """,
            UUID(snapshot_id),
        )

    async def expire_old_snapshots(self, before_ts: datetime) -> int:
        result = await self._pool.execute(
            """
            DELETE FROM working_memory_snapshots
            WHERE expires_at IS NOT NULL AND expires_at < $1
            """,
            before_ts,
        )
        return _rows_from_status(result)

    async def validate_snapshot_checksum(self, snapshot_id: str) -> bool:
        header = await self._pool.fetchrow(
            "SELECT checksum FROM working_memory_snapshots WHERE snapshot_id = $1",
            UUID(snapshot_id),
        )
        if header is None:
            return False
        rows = await self._pool.fetch(
            """
            SELECT point_id, payload_checksum
            FROM working_memory_snapshot_points
            WHERE snapshot_id = $1
            ORDER BY point_id ASC
            """,
            UUID(snapshot_id),
        )
        computed = compute_payload_checksum({"points": [dict(row) for row in rows]})
        return bool(computed == header["checksum"])


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(item)) for item in vector) + "]"


def _point_from_row(row: dict[str, Any]) -> WorkingMemoryPoint:
    vector_value = row.get("memory_vector", [])
    if isinstance(vector_value, str):
        vector = tuple(float(item) for item in vector_value.strip("[]").split(",") if item)
    else:
        vector = tuple(float(item) for item in vector_value)
    return WorkingMemoryPoint(
        point_id=str(row["point_id"]),
        agent_id=str(row["agent_id"]),
        session_id=row["session_id"] if isinstance(row["session_id"], UUID) else UUID(str(row["session_id"])),
        memory_kind=str(row["memory_kind"]),  # type: ignore[arg-type]
        vector=vector,
        vector_dim=int(row["vector_dim"]),
        recency_ts=row["recency_ts"],
        created_at=row["created_at"],
        updated_at=row["created_at"],
        expires_at=row["expires_at"],
        ttl_seconds=max(1, int((row["expires_at"] - row["created_at"]).total_seconds())) if row["expires_at"] else 1,
        embedding_model=str(row["embedding_model"]),
        source_ref=row.get("source_ref"),
        topic=row.get("topic"),
        importance=float(row["importance"]) if row.get("importance") is not None else 0.5,
        safe_summary=row.get("safe_summary"),
        metadata=dict(row.get("metadata") or {}),
    )


def _rows_from_status(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0
