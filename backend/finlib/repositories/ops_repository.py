"""Operational FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    RunAlreadyFinishedError,
    _as_optional_uuid,
    _as_uuid,
    _json_dumps_canonical,
    _require_non_empty,
)
from backend.finlib.repositories.models import (
    AuditContext,
    BatchWriteResult,
    DataQualityCheckInput,
    DataSourceInput,
    IngestionRunInput,
    OutboxEventInput,
    QueuedEvent,
    WatermarkInput,
)


REGISTER_SOURCE_SQL = """
INSERT INTO ops_data_sources(
    source_id, kind, base_url, license_note, methodology_limitations,
    enabled, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (source_id) DO UPDATE SET
    license_note = excluded.license_note,
    methodology_limitations = excluded.methodology_limitations,
    metadata = ops_data_sources.metadata || excluded.metadata
RETURNING (xmax = 0) AS inserted
"""

START_RUN_SQL = """
INSERT INTO ops_ingestion_runs(
    source_id, agent_id, mode, status, source_snapshot_hash, trace_id, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7::jsonb)
RETURNING run_id
"""

FINISH_RUN_SQL = """
UPDATE ops_ingestion_runs
SET status = $2,
    finished_at = now(),
    records_seen = $3,
    records_inserted = $4,
    records_updated = $5,
    records_rejected = $6,
    source_snapshot_hash = $7,
    error_summary = $8,
    metadata = metadata || $9::jsonb
WHERE run_id = $1
  AND finished_at IS NULL
RETURNING run_id
"""

GET_WATERMARK_SQL = """
SELECT *
FROM ops_ingestion_watermarks
WHERE source_id = $1
  AND dataset = $2
"""

SET_WATERMARK_SQL = """
INSERT INTO ops_ingestion_watermarks(
    source_id, dataset, watermark_value, watermark_ts, source_snapshot_hash,
    run_id, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (source_id, dataset) DO UPDATE SET
    watermark_value = excluded.watermark_value,
    watermark_ts = excluded.watermark_ts,
    source_snapshot_hash = excluded.source_snapshot_hash,
    run_id = excluded.run_id,
    updated_at = now(),
    metadata = ops_ingestion_watermarks.metadata || excluded.metadata
WHERE ops_ingestion_watermarks.watermark_ts IS NULL
   OR (
       excluded.watermark_ts IS NOT NULL
       AND excluded.watermark_ts >= ops_ingestion_watermarks.watermark_ts
   )
RETURNING source_id
"""

INSERT_QUALITY_SQL = """
INSERT INTO ops_data_quality_checks(
    run_id, check_name, target_table, severity, passed, observed, expected, metadata
)
VALUES($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb)
RETURNING check_id
"""

INSERT_EVENT_SQL = """
INSERT INTO ops_outbox_events(
    event_type, aggregate_type, aggregate_id, payload, trace_id, run_id, metadata
)
VALUES($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb)
RETURNING event_id
"""

POLL_EVENTS_SQL = """
WITH picked AS (
    SELECT event_id
    FROM ops_outbox_events
    WHERE status = 'pending'
      AND next_attempt_at <= now()
      AND ($1::text[] IS NULL OR event_type = ANY($1::text[]))
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT $2
)
UPDATE ops_outbox_events AS e
SET status = 'processing',
    locked_by = $3,
    locked_at = now(),
    attempts = attempts + 1
FROM picked
WHERE e.event_id = picked.event_id
RETURNING e.*
"""


class OpsRepository(BaseRepository):
    """Repository for FINLIB operational tables."""

    repository_name = "finlib.ops"

    async def register_source(
        self,
        source: DataSourceInput,
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert or update one operational source and append audit."""

        _require_non_empty(source.methodology_limitations, "methodology_limitations")

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            row = await conn.fetchrow(
                REGISTER_SOURCE_SQL,
                source.source_id,
                source.kind,
                source.base_url,
                source.license_note,
                source.methodology_limitations,
                source.enabled,
                _json_dumps_canonical(source.metadata),
            )
            inserted = 1 if row and row["inserted"] else 0
            updated = 0 if inserted else 1
            return BatchWriteResult(1, inserted, updated, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_data_sources",
            operation="upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, 0, audit_id
        )

    async def start_run(
        self,
        run: IngestionRunInput,
        *,
        audit: AuditContext,
    ) -> UUID:
        """Create one ingestion run and append audit."""

        async def work(conn: RepositoryConnection) -> UUID:
            value = await conn.fetchval(
                START_RUN_SQL,
                run.source_id,
                run.agent_id,
                run.mode,
                run.status,
                run.source_snapshot_hash,
                _as_uuid(run.trace_id, "trace_id"),
                _json_dumps_canonical(run.metadata),
            )
            return _as_uuid(value, "run_id")

        run_id, _audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_ingestion_runs",
            operation="insert",
            row_count=1,
            work=work,
        )
        return run_id

    async def finish_run(
        self,
        run_id: UUID | str,
        *,
        status: str,
        audit: AuditContext,
        records_seen: int = 0,
        records_inserted: int = 0,
        records_updated: int = 0,
        records_rejected: int = 0,
        source_snapshot_hash: str | None = None,
        error_summary: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> BatchWriteResult:
        """Finish one run exactly once and append audit."""

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            row = await conn.fetchrow(
                FINISH_RUN_SQL,
                _as_uuid(run_id, "run_id"),
                status,
                records_seen,
                records_inserted,
                records_updated,
                records_rejected,
                source_snapshot_hash,
                error_summary,
                _json_dumps_canonical(metadata or {}),
            )
            if row is None:
                raise RunAlreadyFinishedError("run is already finished or missing")
            return BatchWriteResult(1, 0, 1, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_ingestion_runs",
            operation="update",
            row_count=1,
            work=work,
        )
        return BatchWriteResult(result.attempted, 0, result.updated, 0, audit_id)

    async def get_watermark(
        self,
        *,
        source_id: str,
        dataset: str,
    ) -> dict[str, Any] | None:
        """Return the canonical watermark row for source/dataset."""

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(GET_WATERMARK_SQL, source_id, dataset)
        return None if row is None else dict(row)

    async def set_watermark(
        self,
        watermark: WatermarkInput,
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Advance a source/dataset watermark monotonically and append audit."""

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            row = await conn.fetchrow(
                SET_WATERMARK_SQL,
                watermark.source_id,
                watermark.dataset,
                watermark.watermark_value,
                _as_datetime_or_none(watermark.watermark_ts),
                watermark.source_snapshot_hash,
                _as_optional_uuid(watermark.run_id, "run_id"),
                _json_dumps_canonical(watermark.metadata),
            )
            skipped = 1 if row is None else 0
            updated = 0 if row is None else 1
            return BatchWriteResult(1, 0, updated, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_ingestion_watermarks",
            operation="upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted,
            result.inserted,
            result.updated,
            result.skipped,
            audit_id,
        )

    async def record_quality_check(
        self,
        check: DataQualityCheckInput,
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert one data-quality check and append audit."""

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            await conn.fetchval(
                INSERT_QUALITY_SQL,
                _as_uuid(check.run_id, "run_id"),
                check.check_name,
                check.target_table,
                check.severity,
                check.passed,
                _json_dumps_canonical(check.observed),
                _json_dumps_canonical(check.expected),
                _json_dumps_canonical(check.metadata),
            )
            return BatchWriteResult(1, 1, 0, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_data_quality_checks",
            operation="insert",
            row_count=1,
            work=work,
        )
        return BatchWriteResult(1, result.inserted, 0, 0, audit_id)

    async def enqueue_event(
        self,
        event: OutboxEventInput,
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert one pending outbox event and append audit."""

        self._validate_event_payload(event.payload)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            await conn.fetchval(
                INSERT_EVENT_SQL,
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
                _json_dumps_canonical(event.payload),
                _as_optional_uuid(event.trace_id, "trace_id"),
                _as_optional_uuid(event.run_id, "run_id"),
                _json_dumps_canonical(event.metadata),
            )
            return BatchWriteResult(1, 1, 0, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_outbox_events",
            operation="insert",
            row_count=1,
            work=work,
        )
        return BatchWriteResult(1, result.inserted, 0, 0, audit_id)

    async def poll_events(
        self,
        *,
        limit: int,
        locked_by: str,
        audit: AuditContext,
        event_types: list[str] | None = None,
    ) -> list[QueuedEvent]:
        """Claim pending due events with FOR UPDATE SKIP LOCKED."""

        self._validate_poll_limit(limit)
        _require_non_empty(locked_by, "locked_by")

        async def work(conn: RepositoryConnection) -> list[QueuedEvent]:
            rows = await conn.fetch(POLL_EVENTS_SQL, event_types, limit, locked_by)
            return [_queued_event_from_row(row) for row in rows]

        events, _audit_id = await self._audited_transaction(
            audit=audit,
            target_table="ops_outbox_events",
            operation="update",
            row_count=len,
            work=work,
        )
        return events

    def _validate_poll_limit(self, limit: int) -> None:
        """Validate poll limit for tests and runtime."""

        if limit <= 0:
            raise ValueError("limit must be > 0")

    def _validate_event_payload(self, payload: object) -> None:
        """Reject Level 0 payload fields before enqueue."""

        self._validate_no_level0_payload(payload)


def _queued_event_from_row(row: Any) -> QueuedEvent:
    return QueuedEvent(
        event_id=_as_uuid(row["event_id"], "event_id"),
        event_type=str(row["event_type"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        payload=dict(row["payload"]),
        attempts=int(row["attempts"]),
        locked_by=str(row["locked_by"]),
        locked_at=row["locked_at"],
        run_id=_as_optional_uuid(row["run_id"], "run_id"),
        trace_id=_as_optional_uuid(row["trace_id"], "trace_id"),
        metadata=dict(row["metadata"]),
    )


def _as_datetime_or_none(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
