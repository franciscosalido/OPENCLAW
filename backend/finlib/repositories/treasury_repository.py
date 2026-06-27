"""Treasury FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    _as_uuid,
    _json_dumps_canonical,
)
from backend.finlib.repositories.models import (
    AuditContext,
    BatchWriteResult,
    TreasuryBondInput,
    TreasuryPriceInput,
)


UPSERT_BOND_SQL = """
INSERT INTO treasury_bonds(
    bond_type, security_family, maturity_date, display_name, source_id,
    is_active, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (bond_type, maturity_date) DO UPDATE SET
    display_name = excluded.display_name,
    security_family = excluded.security_family,
    is_active = excluded.is_active,
    metadata = treasury_bonds.metadata || excluded.metadata
RETURNING bond_id, (xmax = 0) AS inserted
"""

INSERT_PRICE_SQL = """
INSERT INTO treasury_prices(
    bond_id, ts, price_bid, price_ask, rate_bid, rate_ask, base_value,
    source_id, run_id, lineage_hash, schema_version, quality_flags, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb)
ON CONFLICT (lineage_hash, ts) DO NOTHING
RETURNING bond_id
"""


class TreasuryRepository(BaseRepository):
    """Repository for Tesouro Direto bonds and temporal prices."""

    repository_name = "finlib.treasury"

    async def upsert_bonds_batch(
        self,
        rows: list[TreasuryBondInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Upsert treasury bonds by natural key and append one audit row."""

        if not rows:
            return BatchWriteResult.empty()

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            updated = 0
            for row in rows:
                result = await conn.fetchrow(
                    UPSERT_BOND_SQL,
                    row.bond_type,
                    row.security_family,
                    _as_date(row.maturity_date),
                    row.display_name,
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
            target_table="treasury_bonds",
            operation="bulk_upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, 0, audit_id
        )

    async def upsert_prices_batch(
        self,
        rows: list[TreasuryPriceInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert treasury prices idempotently and append one audit row."""

        if not rows:
            return BatchWriteResult.empty()

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                inserted_row = await conn.fetchrow(
                    INSERT_PRICE_SQL,
                    _as_uuid(row.bond_id, "bond_id"),
                    _as_datetime(row.ts),
                    _decimal_or_none(row.price_bid),
                    _decimal_or_none(row.price_ask),
                    _decimal_or_none(row.rate_bid),
                    _decimal_or_none(row.rate_ask),
                    _decimal_or_none(row.base_value),
                    row.source_id,
                    _as_uuid(row.run_id, "run_id"),
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.quality_flags),
                    _json_dumps_canonical(row.metadata),
                )
                if inserted_row is None:
                    skipped += 1
                else:
                    inserted += 1
            return BatchWriteResult(len(rows), inserted, 0, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="treasury_prices",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )


def _as_date(value: date | str) -> date:
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
