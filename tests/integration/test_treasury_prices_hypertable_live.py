from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    UniqueViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_hypertable, is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_treasury") as client:
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


async def test_treasury_migration_applies_idempotently(
    postgres_client: PostgresClient,
) -> None:
    async with postgres_client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB treasury tests")

    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)

    assert "023_create_treasury_bonds_prices" in first
    assert second == ()


async def test_treasury_tables_hypertable_and_indexes_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.treasury_bonds')"
        )
        == "treasury_bonds"
    )
    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.treasury_prices')"
        )
        == "treasury_prices"
    )

    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "treasury_prices")

    rows = await postgres_client.pool.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename IN ('treasury_bonds', 'treasury_prices')
        """
    )
    index_names = {str(row["indexname"]) for row in rows}
    assert "treasury_bonds_pkey" in index_names
    assert "treasury_bonds_bond_type_maturity_date_key" in index_names
    assert "treasury_prices_pkey" in index_names
    assert "uq_treasury_prices_lineage_ts" in index_names
    assert "idx_treasury_bonds_type_maturity" in index_names
    assert "idx_treasury_prices_bond_ts_desc" in index_names
    assert "idx_treasury_prices_source_run" in index_names


async def test_treasury_hypertable_chunk_interval_is_one_month_when_exposed(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    row = await postgres_client.pool.fetchrow(
        """
        SELECT *
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'public'
          AND hypertable_name = 'treasury_prices'
        """
    )

    assert row is not None
    values = " ".join(str(value).lower() for value in row.values())
    assert "1 mon" in values or "1 month" in values or "30 days" in values


async def test_treasury_seeded_source_and_cross_sprint_tables_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    source = await postgres_client.pool.fetchrow(
        "SELECT * FROM ops_data_sources WHERE source_id = 'tesouro_transparente'"
    )
    audit_table = await postgres_client.pool.fetchval(
        "SELECT to_regclass('public.audit_agent_writes')"
    )
    quality_table = await postgres_client.pool.fetchval(
        "SELECT to_regclass('public.ops_data_quality_checks')"
    )

    assert source is not None
    assert source["kind"] == "treasury"
    assert "Arquivo diario" in source["methodology_limitations"]
    assert audit_table == "audit_agent_writes"
    assert quality_table == "ops_data_quality_checks"


async def test_treasury_foreign_keys_point_to_ops_and_bonds(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    rows = await postgres_client.pool.fetch(
        """
        SELECT
            conrelid::regclass::text AS source_table,
            confrelid::regclass::text AS target_table
        FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid IN (
              'treasury_bonds'::regclass,
              'treasury_prices'::regclass
          )
        """
    )
    pairs = {(str(row["source_table"]), str(row["target_table"])) for row in rows}

    assert ("treasury_bonds", "ops_data_sources") in pairs
    assert ("treasury_prices", "treasury_bonds") in pairs
    assert ("treasury_prices", "ops_data_sources") in pairs
    assert ("treasury_prices", "ops_ingestion_runs") in pairs


async def test_treasury_bonds_reject_duplicate_natural_key_and_bad_json(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    await postgres_client.pool.execute(
        """
        INSERT INTO treasury_bonds(
            bond_type, security_family, maturity_date, display_name, source_id
        )
        VALUES(
            'Tesouro_Selic', 'LFT', '2029-03-01',
            'Tesouro Selic 2029', 'tesouro_transparente'
        )
        """
    )
    with pytest.raises(UniqueViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_bonds(
                bond_type, security_family, maturity_date, display_name, source_id
            )
            VALUES(
                'Tesouro_Selic', 'LFT', '2029-03-01',
                'Tesouro Selic 2029 duplicate', 'tesouro_transparente'
            )
            """
        )
    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO treasury_bonds(
                bond_type, maturity_date, display_name, source_id, metadata
            )
            VALUES(
                'Tesouro_Selic', '2030-03-01', 'Tesouro Selic 2030',
                'tesouro_transparente', '[]'::jsonb
            )
            """
        )


@pytest.mark.parametrize(
    ("field_name", "sql_value"),
    (
        pytest.param("display_name", "E'\\t'", id="tab-display-name"),
        pytest.param("display_name", "E'\\n'", id="newline-display-name"),
        pytest.param("display_name", "E'\\r'", id="carriage-display-name"),
        pytest.param("display_name", "'   '", id="space-display-name"),
    ),
)
async def test_treasury_bonds_reject_whitespace_only_display_name(
    postgres_client: PostgresClient,
    field_name: str,
    sql_value: str,
) -> None:
    await _migrate(postgres_client)

    values = {"display_name": "'Synthetic Treasury'"}
    values[field_name] = sql_value

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            f"""
            INSERT INTO treasury_bonds(
                bond_type, maturity_date, display_name, source_id
            )
            VALUES(
                'Tesouro_Selic', '2035-03-01',
                {values["display_name"]}, 'tesouro_transparente'
            )
            """
        )
