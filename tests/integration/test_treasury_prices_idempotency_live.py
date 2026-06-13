from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    ForeignKeyViolationError,
    NotNullViolationError,
    UniqueViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

CSV_SAMPLE = """Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha
Tesouro Selic;01/03/2029;12/06/2026;10,35;10,25;15000,12;15001,34;14999,00
"""
LINEAGE_FIELDS = (
    "bond_type",
    "maturity_date",
    "ts",
    "price_bid",
    "price_ask",
    "rate_bid",
    "rate_ask",
    "base_value",
    "source_id",
    "schema_version",
)


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(
        dsn, prefix="finlib_treasury_idempotency"
    ) as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB treasury tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(client: PostgresClient) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, source_snapshot_hash
        )
        VALUES(
            'tesouro_transparente', 'finlib-treasury-test', 'execute',
            'completed', uuidv7(), 'sha256:tesouro-snapshot'
        )
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _create_bond(
    client: PostgresClient,
    *,
    bond_type: str = "Tesouro_Selic",
    maturity_date: str = "2029-03-01",
    display_name: str = "Tesouro Selic 2029",
) -> UUID:
    bond_id = await client.pool.fetchval(
        """
        INSERT INTO treasury_bonds(
            bond_type, security_family, maturity_date, display_name, source_id
        )
        VALUES($1, 'LFT', $2::date, $3, 'tesouro_transparente')
        RETURNING bond_id
        """,
        bond_type,
        date.fromisoformat(maturity_date),
        display_name,
    )
    return UUID(str(bond_id))


async def _insert_price(
    client: PostgresClient,
    *,
    bond_id: UUID,
    run_id: UUID,
    ts: str = "2026-06-12 00:00:00+00",
    price_bid: str | None = "15000.12",
    price_ask: str | None = "15001.34",
    rate_bid: str | None = "10.35",
    rate_ask: str | None = "10.25",
    base_value: str | None = "14999.00",
    lineage_hash: str = "sha256:tesouro-selic-2029-2026-06-12",
) -> str:
    return str(
        await client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, price_ask, rate_bid, rate_ask,
                base_value, source_id, run_id, lineage_hash
            )
            VALUES(
                $1, $2::timestamptz, $3::numeric, $4::numeric, $5::numeric,
                $6::numeric, $7::numeric, 'tesouro_transparente', $8, $9
            )
            """,
            bond_id,
            _timestamp(ts),
            _maybe_decimal(price_bid),
            _maybe_decimal(price_ask),
            _maybe_decimal(rate_bid),
            _maybe_decimal(rate_ask),
            _maybe_decimal(base_value),
            run_id,
            lineage_hash,
        )
    )


def _decimal_br(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def _date_br(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def _timestamp(value: str) -> datetime:
    normalized = value
    if normalized.endswith("+00"):
        normalized = f"{normalized}:00"
    return datetime.fromisoformat(normalized)


def _maybe_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _normalize_bond_type(value: str) -> str:
    mapping = {
        "Tesouro Selic": "Tesouro_Selic",
        "Tesouro IPCA+": "Tesouro_IPCA+",
        "Tesouro IPCA+ com Juros Semestrais": ("Tesouro_IPCA+_Juros_Semestrais"),
        "Tesouro Prefixado": "Tesouro_Prefixado",
        "Tesouro Prefixado com Juros Semestrais": (
            "Tesouro_Prefixado_Juros_Semestrais"
        ),
        "Tesouro RendA+": "Tesouro_Renda+",
        "Tesouro Educa+": "Tesouro_Educa+",
    }
    return mapping[value]


def _lineage_hash(row: dict[str, Any]) -> str:
    payload = {field: str(row[field]) for field in LINEAGE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sample_row() -> dict[str, Any]:
    parsed = next(csv.DictReader(StringIO(CSV_SAMPLE), delimiter=";"))
    ref_ts = datetime.combine(
        _date_br(parsed["Data Base"]), datetime.min.time(), tzinfo=timezone.utc
    )
    row: dict[str, Any] = {
        "bond_type": _normalize_bond_type(parsed["Tipo Titulo"]),
        "maturity_date": _date_br(parsed["Data Vencimento"]).isoformat(),
        "ts": ref_ts.isoformat(),
        "price_bid": _decimal_br(parsed["PU Compra Manha"]),
        "price_ask": _decimal_br(parsed["PU Venda Manha"]),
        "rate_bid": _decimal_br(parsed["Taxa Compra Manha"]),
        "rate_ask": _decimal_br(parsed["Taxa Venda Manha"]),
        "base_value": _decimal_br(parsed["PU Base Manha"]),
        "source_id": "tesouro_transparente",
        "schema_version": 1,
    }
    row["lineage_hash"] = _lineage_hash(row)
    return row


async def test_identical_treasury_price_reingestion_is_noop(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    await _insert_price(postgres_client, bond_id=bond_id, run_id=run_id)
    await postgres_client.pool.execute(
        """
        INSERT INTO treasury_prices(
            bond_id, ts, price_bid, price_ask, rate_bid, rate_ask,
            base_value, source_id, run_id, lineage_hash
        )
        VALUES(
            $1, '2026-06-12 00:00:00+00'::timestamptz,
            15000.12, 15001.34, 10.35, 10.25, 14999.00,
            'tesouro_transparente', $2, 'sha256:tesouro-selic-2029-2026-06-12'
        )
        ON CONFLICT (lineage_hash, ts) DO NOTHING
        """,
        bond_id,
        run_id,
    )

    count = await postgres_client.pool.fetchval("SELECT count(*) FROM treasury_prices")

    assert count == 1


async def test_treasury_price_identity_allows_distinct_bonds_same_ts(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    first_bond = await _create_bond(postgres_client)
    second_bond = await _create_bond(
        postgres_client,
        bond_type="Tesouro_Prefixado",
        maturity_date="2031-01-01",
        display_name="Tesouro Prefixado 2031",
    )

    await _insert_price(
        postgres_client,
        bond_id=first_bond,
        run_id=run_id,
        lineage_hash="sha256:first-bond-same-ts",
    )
    await _insert_price(
        postgres_client,
        bond_id=second_bond,
        run_id=run_id,
        lineage_hash="sha256:second-bond-same-ts",
    )
    with pytest.raises(UniqueViolationError):
        await _insert_price(
            postgres_client,
            bond_id=first_bond,
            run_id=run_id,
            price_bid="15000.13",
            lineage_hash="sha256:first-bond-same-ts-updated",
        )

    count = await postgres_client.pool.fetchval("SELECT count(*) FROM treasury_prices")

    assert count == 2


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        pytest.param("price_bid", "-0.01", id="negative-price-bid"),
        pytest.param("price_ask", "-0.01", id="negative-price-ask"),
        pytest.param("base_value", "-0.01", id="negative-base-value"),
        pytest.param("price_ask", "14999.99", id="price-ask-below-bid"),
        pytest.param("rate_ask", "10.36", id="rate-ask-above-bid"),
    ),
)
async def test_treasury_price_quality_checks_reject_bad_values(
    postgres_client: PostgresClient,
    field_name: str,
    field_value: str,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    with pytest.raises(CheckViolationError):
        if field_name == "price_bid":
            await _insert_price(
                postgres_client,
                bond_id=bond_id,
                run_id=run_id,
                price_bid=field_value,
                lineage_hash=f"sha256:bad-{field_name}-{field_value}",
            )
        elif field_name == "price_ask":
            await _insert_price(
                postgres_client,
                bond_id=bond_id,
                run_id=run_id,
                price_ask=field_value,
                lineage_hash=f"sha256:bad-{field_name}-{field_value}",
            )
        elif field_name == "base_value":
            await _insert_price(
                postgres_client,
                bond_id=bond_id,
                run_id=run_id,
                base_value=field_value,
                lineage_hash=f"sha256:bad-{field_name}-{field_value}",
            )
        elif field_name == "rate_ask":
            await _insert_price(
                postgres_client,
                bond_id=bond_id,
                run_id=run_id,
                rate_ask=field_value,
                lineage_hash=f"sha256:bad-{field_name}-{field_value}",
            )
        else:  # pragma: no cover - parametrization guard.
            raise AssertionError(f"unsupported field: {field_name}")


async def test_treasury_price_allows_negative_rates_when_spread_is_sane(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    await _insert_price(
        postgres_client,
        bond_id=bond_id,
        run_id=run_id,
        rate_bid="-0.05",
        rate_ask="-0.10",
        lineage_hash="sha256:negative-rates-sane-spread",
    )

    row = await postgres_client.pool.fetchrow(
        """
        SELECT rate_bid, rate_ask
        FROM treasury_prices
        WHERE lineage_hash = 'sha256:negative-rates-sane-spread'
        """
    )

    assert row is not None
    assert row["rate_bid"] == Decimal("-0.05")
    assert row["rate_ask"] == Decimal("-0.10")


async def test_treasury_price_requires_at_least_one_observation(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    with pytest.raises(CheckViolationError):
        await _insert_price(
            postgres_client,
            bond_id=bond_id,
            run_id=run_id,
            price_bid=None,
            price_ask=None,
            rate_bid=None,
            rate_ask=None,
            base_value=None,
            lineage_hash="sha256:all-null-observation",
        )


async def test_treasury_price_rejects_future_ts(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)
    future_ts = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    with pytest.raises(CheckViolationError):
        await _insert_price(
            postgres_client,
            bond_id=bond_id,
            run_id=run_id,
            ts=future_ts,
            lineage_hash="sha256:future-ts",
        )


async def test_treasury_price_rejects_missing_fk_and_lineage(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, source_id, run_id, lineage_hash
            )
            VALUES(
                $1, '2026-06-12 00:00:00+00'::timestamptz, 15000.12,
                'missing_source', $2, 'sha256:missing-source'
            )
            """,
            bond_id,
            run_id,
        )

    with pytest.raises(ForeignKeyViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, source_id, run_id, lineage_hash
            )
            VALUES(
                $1, '2026-06-12 00:00:00+00'::timestamptz, 15000.12,
                'tesouro_transparente',
                '00000000-0000-7000-8000-000000000001'::uuid,
                'sha256:missing-run'
            )
            """,
            bond_id,
        )

    with pytest.raises(NotNullViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, source_id, run_id
            )
            VALUES(
                $1, '2026-06-12 00:00:00+00'::timestamptz, 15000.12,
                'tesouro_transparente', $2
            )
            """,
            bond_id,
            run_id,
        )

    with pytest.raises(CheckViolationError):
        await _insert_price(
            postgres_client,
            bond_id=bond_id,
            run_id=run_id,
            lineage_hash="\t",
        )


async def test_treasury_price_rejects_json_arrays(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(postgres_client)

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, source_id, run_id, lineage_hash,
                quality_flags
            )
            VALUES(
                $1, '2026-06-12 00:00:00+00'::timestamptz, 15000.12,
                'tesouro_transparente', $2, 'sha256:bad-quality-flags',
                '[]'::jsonb
            )
            """,
            bond_id,
            run_id,
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_prices(
                bond_id, ts, price_bid, source_id, run_id, lineage_hash,
                metadata
            )
            VALUES(
                $1, '2026-06-12 00:00:00+00'::timestamptz, 15000.12,
                'tesouro_transparente', $2, 'sha256:bad-metadata', '[]'::jsonb
            )
            """,
            bond_id,
            run_id,
        )


async def test_csv_sample_normalizes_and_inserts_treasury_price(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    row = _sample_row()
    run_id = await _create_run(postgres_client)
    bond_id = await _create_bond(
        postgres_client,
        bond_type=str(row["bond_type"]),
        maturity_date=str(row["maturity_date"]),
        display_name="Tesouro Selic 2029",
    )

    await _insert_price(
        postgres_client,
        bond_id=bond_id,
        run_id=run_id,
        ts=str(row["ts"]),
        price_bid=str(row["price_bid"]),
        price_ask=str(row["price_ask"]),
        rate_bid=str(row["rate_bid"]),
        rate_ask=str(row["rate_ask"]),
        base_value=str(row["base_value"]),
        lineage_hash=str(row["lineage_hash"]),
    )

    stored = await postgres_client.pool.fetchrow(
        "SELECT * FROM treasury_prices WHERE bond_id = $1 AND ts = $2::timestamptz",
        bond_id,
        _timestamp(str(row["ts"])),
    )

    assert stored is not None
    assert stored["price_bid"] == Decimal("15000.12")
    assert stored["price_ask"] == Decimal("15001.34")
    assert stored["rate_bid"] == Decimal("10.35")
    assert stored["rate_ask"] == Decimal("10.25")
    assert stored["base_value"] == Decimal("14999.00")
    assert stored["lineage_hash"] == row["lineage_hash"]
