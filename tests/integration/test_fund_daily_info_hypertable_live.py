from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from asyncpg.exceptions import CheckViolationError  # type: ignore[import-untyped]

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
    async with isolated_postgres_client(dsn, prefix="finlib_fund") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB fund tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def test_fund_migration_applies_idempotently(
    postgres_client: PostgresClient,
) -> None:
    async with postgres_client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB fund tests")

    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)

    assert "024_create_fund_registry_daily_info" in first
    assert second == ()


async def test_fund_tables_hypertable_and_indexes_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.fund_registry')"
        )
        == "fund_registry"
    )
    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.fund_daily_info')"
        )
        == "fund_daily_info"
    )

    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "fund_daily_info")
        assert not await is_hypertable(conn, "fund_registry")

    rows = await postgres_client.pool.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename IN ('fund_registry', 'fund_daily_info')
        """
    )
    index_names = {str(row["indexname"]) for row in rows}
    assert "fund_registry_pkey" in index_names
    assert "fund_daily_info_pkey" in index_names
    assert "uq_fund_daily_info_lineage_ts" in index_names
    assert "idx_fund_registry_source_id" in index_names
    assert "idx_fund_daily_info_fund_ts_desc" in index_names
    assert "idx_fund_daily_info_source_run" in index_names


async def test_fund_hypertable_dimension_and_unique_indexes_include_ts(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    dimension = await postgres_client.pool.fetchrow(
        """
        SELECT *
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'public'
          AND hypertable_name = 'fund_daily_info'
        """
    )
    constraints = await postgres_client.pool.fetch(
        """
        SELECT conname, array_agg(att.attname ORDER BY ord.ordinality) AS columns
        FROM pg_constraint AS con
        JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, ordinality)
          ON TRUE
        JOIN pg_attribute AS att
          ON att.attrelid = con.conrelid
         AND att.attnum = ord.attnum
        WHERE con.conrelid = 'fund_daily_info'::regclass
          AND con.contype IN ('p', 'u')
        GROUP BY con.conname
        """
    )

    assert dimension is not None
    values = " ".join(str(value).lower() for value in dimension.values())
    assert "ts" in values
    assert "1 mon" in values or "1 month" in values or "30 days" in values
    for row in constraints:
        assert "ts" in {str(column) for column in row["columns"]}


async def test_fund_seeded_source_and_cross_sprint_tables_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    source = await postgres_client.pool.fetchrow(
        "SELECT * FROM ops_data_sources WHERE source_id = 'cvm_informes_diarios'"
    )
    for table_name in (
        "ops_data_quality_checks",
        "audit_agent_writes",
        "macro_series_catalog",
        "macro_observations",
        "treasury_bonds",
        "treasury_prices",
    ):
        assert (
            await postgres_client.pool.fetchval(
                f"SELECT to_regclass('public.{table_name}')"
            )
            == table_name
        )

    assert source is not None
    assert source["kind"] == "regulator"
    assert "CSV compactado" in source["methodology_limitations"]


async def test_fund_foreign_keys_point_to_ops_and_registry(
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
              'fund_registry'::regclass,
              'fund_daily_info'::regclass
          )
        """
    )
    pairs = {(str(row["source_table"]), str(row["target_table"])) for row in rows}

    assert ("fund_registry", "ops_data_sources") in pairs
    assert ("fund_daily_info", "fund_registry") in pairs
    assert ("fund_daily_info", "ops_data_sources") in pairs
    assert ("fund_daily_info", "ops_ingestion_runs") in pairs


@pytest.mark.parametrize(
    ("field_name", "sql_value"),
    (
        pytest.param("legal_name", "E'\\t'", id="tab-legal-name"),
        pytest.param("legal_name", "E'\\n'", id="newline-legal-name"),
        pytest.param("legal_name", "E'\\r'", id="carriage-legal-name"),
        pytest.param("legal_name", "'   '", id="space-legal-name"),
    ),
)
async def test_fund_registry_rejects_whitespace_only_required_text(
    postgres_client: PostgresClient,
    field_name: str,
    sql_value: str,
) -> None:
    await _migrate(postgres_client)
    values = {"legal_name": "'Synthetic Fund'"}
    values[field_name] = sql_value

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            f"""
            INSERT INTO fund_registry(fund_cnpj, legal_name, source_id)
            VALUES('12345678000190', {values["legal_name"]}, 'cvm_informes_diarios')
            """
        )


@pytest.mark.parametrize(
    "fund_cnpj",
    ("12.345.678/0001-90", "123", "abcdefghijklmn"),
)
async def test_fund_registry_rejects_invalid_cnpj(
    postgres_client: PostgresClient,
    fund_cnpj: str,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_registry(fund_cnpj, legal_name, source_id)
            VALUES($1, 'Synthetic Fund', 'cvm_informes_diarios')
            """,
            fund_cnpj,
        )


async def test_fund_json_fields_require_objects(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO fund_registry(fund_cnpj, legal_name, source_id, metadata)
            VALUES('12345678000190', 'Synthetic Fund', 'cvm_informes_diarios', '[]'::jsonb)
            """
        )
