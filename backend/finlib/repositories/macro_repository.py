"""Macro FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    RepositoryIntegrityError,
    _as_uuid,
    _json_dumps_canonical,
)
from backend.finlib.repositories.models import (
    AuditContext,
    BatchWriteResult,
    MacroObservationInput,
    MacroSeriesInput,
)


UPSERT_SERIES_SQL = """
INSERT INTO macro_series_catalog(
    series_code, display_name, provider, provider_code, provider_code_status,
    source_id, original_source, unit, periodicity, value_type, methodology_note,
    requires_live_verification, enabled, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
ON CONFLICT (series_code) DO UPDATE SET
    display_name = excluded.display_name,
    provider = excluded.provider,
    provider_code = excluded.provider_code,
    provider_code_status = excluded.provider_code_status,
    original_source = excluded.original_source,
    unit = excluded.unit,
    periodicity = excluded.periodicity,
    value_type = excluded.value_type,
    methodology_note = excluded.methodology_note,
    requires_live_verification = excluded.requires_live_verification,
    enabled = excluded.enabled,
    metadata = macro_series_catalog.metadata || excluded.metadata
WHERE macro_series_catalog.source_id = excluded.source_id
RETURNING (xmax = 0) AS inserted
"""

LINEAGE_EXISTS_SQL = """
SELECT 1 FROM macro_observations
WHERE lineage_hash = $1
  AND ref_ts = $2
"""

LOCK_MACRO_SLOT_SQL = """
SELECT pg_advisory_xact_lock(hashtext('macro:' || $1 || ':' || $2::text))
"""

NEXT_REVISION_SQL = """
SELECT COALESCE(MAX(revision), -1) + 1
FROM macro_observations
WHERE series_code = $1
  AND ref_ts = $2
"""

INSERT_OBSERVATION_SQL = """
INSERT INTO macro_observations(
    series_code, ref_ts, revision, value, source_id, run_id, lineage_hash,
    schema_version, quality_flags, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb)
"""


class MacroRepository(BaseRepository):
    """Repository for macro catalog and observations."""

    repository_name = "finlib.macro"

    async def upsert_series_catalog(
        self,
        rows: list[MacroSeriesInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Upsert macro series catalog rows and append one audit row."""

        if not rows:
            return BatchWriteResult.empty()

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            updated = 0
            for row in rows:
                result = await conn.fetchrow(
                    UPSERT_SERIES_SQL,
                    row.series_code,
                    row.display_name,
                    row.provider,
                    row.provider_code,
                    row.provider_code_status,
                    row.source_id,
                    row.original_source,
                    row.unit,
                    row.periodicity,
                    row.value_type,
                    row.methodology_note,
                    row.requires_live_verification,
                    row.enabled,
                    _json_dumps_canonical(row.metadata),
                )
                if result is None:
                    raise RepositoryIntegrityError("source_id changed for macro series")
                if result["inserted"]:
                    inserted += 1
                else:
                    updated += 1
            return BatchWriteResult(len(rows), inserted, updated, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="macro_series_catalog",
            operation="bulk_upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, result.skipped, audit_id
        )

    async def upsert_observations_batch(
        self,
        rows: list[MacroObservationInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert macro observations with append-only revision semantics."""

        if not rows:
            return BatchWriteResult.empty()

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                ref_ts = _as_datetime(row.ref_ts)
                await conn.execute(LOCK_MACRO_SLOT_SQL, row.series_code, ref_ts)
                existing = await conn.fetchrow(
                    LINEAGE_EXISTS_SQL,
                    row.lineage_hash,
                    ref_ts,
                )
                if existing is not None:
                    skipped += 1
                    continue
                revision = await conn.fetchval(
                    NEXT_REVISION_SQL,
                    row.series_code,
                    ref_ts,
                )
                await conn.execute(
                    INSERT_OBSERVATION_SQL,
                    row.series_code,
                    ref_ts,
                    revision,
                    Decimal(str(row.value)),
                    row.source_id,
                    _as_uuid(row.run_id, "run_id"),
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.quality_flags),
                    _json_dumps_canonical(row.metadata),
                )
                inserted += 1
            return BatchWriteResult(len(rows), inserted, 0, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="macro_observations",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
