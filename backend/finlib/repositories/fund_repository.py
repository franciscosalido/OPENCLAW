"""Fund FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    _as_uuid,
    _json_dumps_canonical,
)
from backend.finlib.repositories.models import AuditContext, BatchWriteResult
from backend.finlib.repositories.models_assets import (
    FundDailyInfoInput,
    FundRegistryInput,
)


UPSERT_FUND_REGISTRY_SQL = """
INSERT INTO fund_registry(
    fund_cnpj, legal_name, cvm_class, fund_type, status, registered_at,
    source_id, is_active, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9::text::jsonb)
ON CONFLICT (fund_cnpj) DO UPDATE SET
    legal_name = excluded.legal_name,
    cvm_class = excluded.cvm_class,
    fund_type = excluded.fund_type,
    status = excluded.status,
    registered_at = excluded.registered_at,
    source_id = excluded.source_id,
    is_active = excluded.is_active,
    metadata = fund_registry.metadata || excluded.metadata
RETURNING (xmax = 0) AS inserted
"""

FUND_DAILY_LINEAGE_EXISTS_SQL = """
SELECT 1 FROM fund_daily_info
WHERE lineage_hash = $1
  AND ts = $2
"""

LOCK_FUND_DAILY_SLOT_SQL = """
SELECT pg_advisory_xact_lock(hashtext('fund_daily_info:' || $1 || ':' || $2::text))
"""

NEXT_FUND_DAILY_REVISION_SQL = """
SELECT COALESCE(MAX(revision), -1) + 1
FROM fund_daily_info
WHERE fund_cnpj = $1
  AND ts = $2
"""

INSERT_FUND_DAILY_SQL = """
INSERT INTO fund_daily_info(
    fund_cnpj, ts, revision, total_portfolio_value, quota_value, net_worth,
    inflow, outflow, shareholders, source_id, run_id, lineage_hash,
    schema_version, quality_flags, metadata
)
VALUES(
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
    $14::text::jsonb, $15::text::jsonb
)
"""


class FundRepository(BaseRepository):
    """Repository for CVM fund registry and daily information."""

    repository_name = "finlib.fund"

    async def upsert_registry_batch(
        self,
        rows: list[FundRegistryInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Upsert fund registry rows by fund_cnpj and append one audit row."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            updated = 0
            for row in rows:
                result = await conn.fetchrow(
                    UPSERT_FUND_REGISTRY_SQL,
                    row.fund_cnpj,
                    row.legal_name,
                    row.cvm_class,
                    row.fund_type,
                    row.status,
                    _as_date_or_none(row.registered_at),
                    row.source_id,
                    row.is_active,
                    _json_dumps_canonical(row.metadata),
                )
                if result and result["inserted"]:
                    inserted += 1
                else:
                    updated += 1
            return BatchWriteResult(len(rows), inserted, updated, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="fund_registry",
            operation="bulk_upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, result.skipped, audit_id
        )

    async def upsert_daily_info_batch(
        self,
        rows: list[FundDailyInfoInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert fund daily rows with append-only revision semantics."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.quality_flags)
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                ts = _as_datetime(row.ts)
                await conn.execute(LOCK_FUND_DAILY_SLOT_SQL, row.fund_cnpj, ts)
                existing = await conn.fetchrow(
                    FUND_DAILY_LINEAGE_EXISTS_SQL,
                    row.lineage_hash,
                    ts,
                )
                if existing is not None:
                    skipped += 1
                    continue
                revision = await conn.fetchval(
                    NEXT_FUND_DAILY_REVISION_SQL,
                    row.fund_cnpj,
                    ts,
                )
                await conn.execute(
                    INSERT_FUND_DAILY_SQL,
                    row.fund_cnpj,
                    ts,
                    revision,
                    _decimal_or_none(row.total_portfolio_value),
                    Decimal(str(row.quota_value)),
                    Decimal(str(row.net_worth)),
                    _decimal_or_none(row.inflow),
                    _decimal_or_none(row.outflow),
                    row.shareholders,
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
            target_table="fund_daily_info",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )


def _as_date_or_none(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decimal_or_none(value: Decimal | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
