"""Private fixed-income FINLIB repository over asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from backend.finlib.rate_spec import RateSpec, validate_rate_spec_for_instrument
from backend.finlib.repositories.base import (
    BaseRepository,
    RepositoryConnection,
    _as_optional_uuid,
    _as_uuid,
    _json_dumps_canonical,
)
from backend.finlib.repositories.models import AuditContext, BatchWriteResult
from backend.finlib.repositories.models_assets import (
    DebentureMarketDataInput,
    FixedIncomeInstrumentInput,
)


INSERT_FI_INSTRUMENT_SQL = """
INSERT INTO fi_instruments(
    kind, issuer_cnpj, issuer_name, instrument_name, isin, indexer, rate_spec,
    fgc_covered, issue_date, maturity_date, source_id, run_id, lineage_hash,
    schema_version, quality_flags, metadata
)
VALUES(
    $1, $2, $3, $4, $5, $6, $7::text::jsonb, $8, $9, $10, $11, $12, $13,
    $14, $15::text::jsonb, $16::text::jsonb
)
ON CONFLICT (lineage_hash) DO NOTHING
RETURNING instrument_id
"""

DEBENTURE_LINEAGE_EXISTS_SQL = """
SELECT 1 FROM debenture_market_data
WHERE lineage_hash = $1
  AND ts = $2
"""

LOCK_DEBENTURE_SLOT_SQL = """
SELECT pg_advisory_xact_lock(
    hashtext('debenture_market_data:' || $1::uuid::text || ':' || $2::timestamptz::text)
)
"""

NEXT_DEBENTURE_REVISION_SQL = """
SELECT COALESCE(MAX(revision), -1) + 1
FROM debenture_market_data
WHERE fi_id = $1
  AND ts = $2
"""

INSERT_DEBENTURE_MARKET_DATA_SQL = """
INSERT INTO debenture_market_data(
    fi_id, ts, revision, indicative_rate, pu, duration, source_id, run_id,
    lineage_hash, schema_version, quality_flags, metadata
)
VALUES(
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
    $11::text::jsonb, $12::text::jsonb
)
ON CONFLICT (lineage_hash, ts) DO NOTHING
RETURNING fi_id
"""


class FixedIncomeRepository(BaseRepository):
    """Repository for private fixed-income instruments and debenture data."""

    repository_name = "finlib.fixed_income"

    async def upsert_instruments_batch(
        self,
        rows: list[FixedIncomeInstrumentInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert fixed-income instruments idempotently by lineage_hash."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.metadata)
            self._validate_no_level0_payload(row.quality_flags)
            self._validate_no_level0_payload(_rate_spec_payload(row))

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                rate_spec = validate_rate_spec_for_instrument(
                    kind=row.kind,
                    indexer=row.indexer,
                    rate_spec=row.rate_spec,
                    issuer_cnpj=row.issuer_cnpj,
                )
                result = await conn.fetchrow(
                    INSERT_FI_INSTRUMENT_SQL,
                    row.kind,
                    row.issuer_cnpj,
                    row.issuer_name,
                    row.instrument_name,
                    row.isin,
                    row.indexer,
                    _json_dumps_canonical(rate_spec.canonical_payload()),
                    row.fgc_covered,
                    _as_date_or_none(row.issue_date),
                    _as_date_or_none(row.maturity_date),
                    row.source_id,
                    _as_optional_uuid(row.run_id, "run_id"),
                    row.lineage_hash,
                    row.schema_version,
                    _json_dumps_canonical(row.quality_flags),
                    _json_dumps_canonical(row.metadata),
                )
                if result is None:
                    skipped += 1
                else:
                    inserted += 1
            return BatchWriteResult(len(rows), inserted, 0, skipped, None)

        result, audit_id = await self._audited_transaction(
            audit=audit,
            target_table="fi_instruments",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )

    async def upsert_debenture_market_data_batch(
        self,
        rows: list[DebentureMarketDataInput],
        *,
        audit: AuditContext,
    ) -> BatchWriteResult:
        """Insert debenture market observations with revision semantics."""

        if not rows:
            return BatchWriteResult.empty()
        for row in rows:
            self._validate_no_level0_payload(row.quality_flags)
            self._validate_no_level0_payload(row.metadata)

        async def work(conn: RepositoryConnection) -> BatchWriteResult:
            inserted = 0
            skipped = 0
            for row in rows:
                fi_id = _as_uuid(row.fi_id, "fi_id")
                ts = _as_datetime(row.ts)
                await conn.execute(LOCK_DEBENTURE_SLOT_SQL, fi_id, ts)
                existing = await conn.fetchrow(
                    DEBENTURE_LINEAGE_EXISTS_SQL,
                    row.lineage_hash,
                    ts,
                )
                if existing is not None:
                    skipped += 1
                    continue
                revision = await conn.fetchval(
                    NEXT_DEBENTURE_REVISION_SQL,
                    fi_id,
                    ts,
                )
                inserted_row = await conn.fetchrow(
                    INSERT_DEBENTURE_MARKET_DATA_SQL,
                    fi_id,
                    ts,
                    revision,
                    _decimal_or_none(row.indicative_rate),
                    _decimal_or_none(row.pu),
                    row.duration,
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
            target_table="debenture_market_data",
            operation="bulk_insert",
            row_count=lambda result: result.inserted,
            work=work,
        )
        return BatchWriteResult(
            result.attempted, result.inserted, 0, result.skipped, audit_id
        )


def _rate_spec_payload(row: FixedIncomeInstrumentInput) -> dict[str, object]:
    if isinstance(row.rate_spec, RateSpec):
        return row.rate_spec.canonical_payload()
    return dict(row.rate_spec)


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
