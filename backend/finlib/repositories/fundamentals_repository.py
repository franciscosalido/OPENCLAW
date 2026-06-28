"""Company fundamentals FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from backend.finlib.fundamentals import MARKET_DEPENDENT_INDICATORS
from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    RepositoryIntegrityError,
    _as_uuid,
    _json_dumps_canonical,
    _require_non_empty,
)
from backend.finlib.repositories.models import AuditContext, BatchWriteResult
from backend.finlib.repositories.models_assets import (
    CompanyListingInput,
    CompanyRegistryInput,
    FundamentalsIndicatorInput,
    FundamentalsStatementInput,
)


UPSERT_COMPANY_REGISTRY_SQL = """
INSERT INTO company_registry(
    cnpj, cnpj_base, legal_name, trade_name, sector_ibge, cvm_code,
    cvm_category, listing_status, source_id, lineage_hash, schema_version,
    metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::text::jsonb)
ON CONFLICT (cnpj) DO UPDATE SET
    cnpj_base = excluded.cnpj_base,
    legal_name = excluded.legal_name,
    trade_name = excluded.trade_name,
    sector_ibge = excluded.sector_ibge,
    cvm_code = excluded.cvm_code,
    cvm_category = excluded.cvm_category,
    listing_status = excluded.listing_status,
    source_id = excluded.source_id,
    lineage_hash = excluded.lineage_hash,
    schema_version = excluded.schema_version,
    metadata = company_registry.metadata || excluded.metadata
RETURNING company_id, (xmax = 0) AS inserted
"""

UPSERT_COMPANY_LISTING_SQL = """
INSERT INTO company_listings(
    company_id, exchange, ticker, share_class, isin, lot_size, active,
    listed_at, delisted_at, source_id, lineage_hash, schema_version, metadata
)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::text::jsonb)
ON CONFLICT (exchange, ticker) DO UPDATE SET
    share_class = excluded.share_class,
    isin = excluded.isin,
    lot_size = excluded.lot_size,
    active = excluded.active,
    listed_at = excluded.listed_at,
    delisted_at = excluded.delisted_at,
    source_id = excluded.source_id,
    lineage_hash = excluded.lineage_hash,
    schema_version = excluded.schema_version,
    metadata = company_listings.metadata || excluded.metadata
RETURNING listing_id, (xmax = 0) AS inserted
"""

STATEMENT_LINEAGE_EXISTS_SQL = """
SELECT 1 FROM fundamentals_statements
WHERE lineage_hash = $1
"""

LOCK_STATEMENT_SLOT_SQL = """
SELECT pg_advisory_xact_lock(
    hashtext(
        'fundamentals_statement:' || $1::uuid::text || ':' || $2 || ':' || $3
        || ':' || $4 || ':' || $5::date::text
    )
)
"""

LATEST_STATEMENT_VERSION_SQL = """
SELECT statement_id, version
FROM fundamentals_statements
WHERE company_id = $1
  AND period_type = $2
  AND period_kind = $3
  AND statement_scope = $4
  AND period_end = $5
ORDER BY version DESC
LIMIT 1
"""

INSERT_STATEMENT_SQL = """
INSERT INTO fundamentals_statements(
    company_id, period_type, period_kind, statement_scope, fiscal_year,
    fiscal_quarter, period_end, filing_date, version, restatement_reason,
    prior_version_id, statements_json, currency, unit_multiplier, source_id,
    run_id, lineage_hash, schema_version, quality_flags, metadata
)
VALUES(
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
    $12::text::jsonb, $13, $14, $15, $16, $17, $18,
    $19::text::jsonb, $20::text::jsonb
)
RETURNING statement_id
"""

INSERT_INDICATORS_SQL = """
INSERT INTO fundamentals_indicators(
    company_id, ts, indicator_set, source_statement_id, indicators_json,
    computation_hash, run_id, lineage_hash, schema_version, quality_flags,
    metadata
)
VALUES(
    $1, $2, $3, $4, $5::text::jsonb, $6, $7, $8, $9,
    $10::text::jsonb, $11::text::jsonb
)
ON CONFLICT (lineage_hash, ts) DO NOTHING
RETURNING company_id
"""


class FundamentalsRepository(BaseRepository):
    """Repository for company registry, listings, statements and indicators."""

    repository_name = "finlib.fundamentals"

    async def upsert_company_registry_batch(
        self,
        rows: list[CompanyRegistryInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Upsert companies by CNPJ and append one audit row."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            updated = 0
            for row in rows:
                result = await conn.fetchrow(
                    UPSERT_COMPANY_REGISTRY_SQL,
                    row.cnpj,
                    row.cnpj_base,
                    row.legal_name,
                    row.trade_name,
                    row.sector_ibge,
                    row.cvm_code,
                    row.cvm_category,
                    row.listing_status,
                    row.source_id,
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.metadata),
                )
                if result and result["inserted"]:
                    inserted += 1
                else:
                    updated += 1
            return BatchWriteResult(len(rows), inserted, updated, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="company_registry",
            operation="bulk_upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, result.skipped, audit_id
        )

    async def upsert_company_listings_batch(
        self,
        rows: list[CompanyListingInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Upsert listings by exchange/ticker without changing company_id."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            updated = 0
            for row in rows:
                result = await conn.fetchrow(
                    UPSERT_COMPANY_LISTING_SQL,
                    _as_uuid(row.company_id, "company_id"),
                    row.exchange,
                    row.ticker,
                    row.share_class,
                    row.isin,
                    row.lot_size,
                    row.active,
                    _as_date_or_none(row.listed_at),
                    _as_date_or_none(row.delisted_at),
                    row.source_id,
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.metadata),
                )
                if result and result["inserted"]:
                    inserted += 1
                else:
                    updated += 1
            return BatchWriteResult(len(rows), inserted, updated, 0, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="company_listings",
            operation="bulk_upsert",
            row_count=lambda result: result.inserted + result.updated,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, result.updated, result.skipped, audit_id
        )

    async def upsert_statements_batch(
        self,
        rows: list[FundamentalsStatementInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert statements with append-only restatement semantics."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.statements_json)
            self._validate_no_level0_payload(row.quality_flags)
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                company_id = _as_uuid(row.company_id, "company_id")
                period_end = _as_date(row.period_end)
                await conn.execute(
                    LOCK_STATEMENT_SLOT_SQL,
                    company_id,
                    row.period_type,
                    row.period_kind,
                    row.statement_scope,
                    period_end,
                )
                existing = await conn.fetchrow(
                    STATEMENT_LINEAGE_EXISTS_SQL,
                    row.lineage_hash,
                )
                if existing is not None:
                    skipped += 1
                    continue
                latest = await conn.fetchrow(
                    LATEST_STATEMENT_VERSION_SQL,
                    company_id,
                    row.period_type,
                    row.period_kind,
                    row.statement_scope,
                    period_end,
                )
                version = 1
                prior_version_id: UUID | None = None
                restatement_reason: str | None = None
                if latest is not None:
                    version = int(latest["version"]) + 1
                    prior_version_id = _as_uuid(
                        latest["statement_id"],
                        "prior_version_id",
                    )
                    restatement_reason = _require_non_empty(
                        row.restatement_reason or "",
                        "restatement_reason",
                    )
                returned = await conn.fetchval(
                    INSERT_STATEMENT_SQL,
                    company_id,
                    row.period_type,
                    row.period_kind,
                    row.statement_scope,
                    row.fiscal_year,
                    row.fiscal_quarter,
                    period_end,
                    _as_date(row.filing_date),
                    version,
                    restatement_reason,
                    prior_version_id,
                    _json_dumps_canonical(row.statements_json),
                    row.currency,
                    row.unit_multiplier,
                    row.source_id,
                    _as_uuid(row.run_id, "run_id"),
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.quality_flags),
                    _json_dumps_canonical(row.metadata),
                )
                if returned is None:
                    raise RepositoryIntegrityError("statement insert returned no row")
                inserted += 1
            return BatchWriteResult(len(rows), inserted, 0, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="fundamentals_statements",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )

    async def upsert_indicators_batch(
        self,
        rows: list[FundamentalsIndicatorInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert precomputed statement-only indicators idempotently."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.indicators_json)
            self._validate_no_level0_payload(row.quality_flags)
            self._validate_no_level0_payload(row.metadata)
            _reject_market_dependent_indicators(row.indicators_json)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                returned = await conn.fetchrow(
                    INSERT_INDICATORS_SQL,
                    _as_uuid(row.company_id, "company_id"),
                    _as_datetime(row.ts),
                    row.indicator_set,
                    _as_uuid(row.source_statement_id, "source_statement_id"),
                    _json_dumps_canonical(row.indicators_json),
                    row.computation_hash,
                    _as_uuid(row.run_id, "run_id"),
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.quality_flags),
                    _json_dumps_canonical(row.metadata),
                )
                if returned is None:
                    skipped += 1
                else:
                    inserted += 1
            return BatchWriteResult(len(rows), inserted, 0, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="fundamentals_indicators",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )


def _reject_market_dependent_indicators(payload: dict[str, object]) -> None:
    forbidden = sorted(MARKET_DEPENDENT_INDICATORS.intersection(payload))
    if forbidden:
        joined = ", ".join(forbidden)
        raise ValueError(f"market-dependent indicators are not allowed: {joined}")


def _as_date_or_none(value: date | str | None) -> date | None:
    if value is None:
        return None
    return _as_date(value)


def _as_date(value: date | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
