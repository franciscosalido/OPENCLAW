from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from asyncpg.exceptions import (  # type: ignore[import-untyped]
    CheckViolationError,
    NotNullViolationError,
)

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_hypertable, is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

EXPECTED_SERIES = {
    "ipca",
    "igpm",
    "selic_meta",
    "selic_diaria",
    "cdi",
    "ptax_usdbrl_compra",
    "ptax_usdbrl_venda",
}
DERIVED_FX_CODES = {
    "brlusd",
    "brl_usd",
    "fx_brlusd",
    "brlusd_mid",
    "usdbrl_mid",
}


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_macro") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB macro tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def test_macro_migration_applies_idempotently(
    postgres_client: PostgresClient,
) -> None:
    async with postgres_client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB macro tests")

    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)

    assert "022_create_macro_catalog_observations" in first
    assert second == ()


async def test_macro_tables_view_hypertable_and_indexes_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.macro_series_catalog')"
        )
        == "macro_series_catalog"
    )
    assert (
        await postgres_client.pool.fetchval(
            "SELECT to_regclass('public.macro_observations')"
        )
        == "macro_observations"
    )
    relkind = await postgres_client.pool.fetchval(
        """
        SELECT relkind::text
        FROM pg_class
        WHERE oid = 'public.vw_fx_brlusd'::regclass
        """
    )
    assert str(relkind) == "v"

    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "macro_observations")

    rows = await postgres_client.pool.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'macro_observations'
        """
    )
    index_names = {str(row["indexname"]) for row in rows}
    assert "macro_observations_pkey" in index_names
    assert "uq_macro_observations_lineage_ref_ts" in index_names
    assert "idx_macro_observations_series_ref_ts" in index_names
    assert "idx_macro_observations_source_run" in index_names


async def test_macro_hypertable_chunk_interval_is_three_months_when_exposed(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    row = await postgres_client.pool.fetchrow(
        """
        SELECT *
        FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'public'
          AND hypertable_name = 'macro_observations'
        """
    )

    assert row is not None
    values = " ".join(str(value).lower() for value in row.values())
    assert "3 mons" in values or "3 months" in values or "90 days" in values


async def test_macro_seeded_bcb_sgs_source_and_catalog_rows(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    source = await postgres_client.pool.fetchrow(
        "SELECT * FROM ops_data_sources WHERE source_id = 'bcb_sgs'"
    )
    rows = await postgres_client.pool.fetch(
        """
        SELECT series_code, provider, source_id, provider_code_status,
               requires_live_verification
        FROM macro_series_catalog
        ORDER BY series_code
        """
    )

    assert source is not None
    assert source["kind"] == "central_bank"
    assert "catalogo vivo/API" in source["methodology_limitations"]

    series_codes = {str(row["series_code"]) for row in rows}
    assert series_codes == EXPECTED_SERIES
    assert series_codes.isdisjoint(DERIVED_FX_CODES)
    for row in rows:
        assert row["provider"] == "bcb_sgs"
        assert row["source_id"] == "bcb_sgs"
        assert row["provider_code_status"] == "planning_reference"
        assert row["requires_live_verification"] is True


async def test_macro_foreign_keys_point_to_ops_tables(
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
              'macro_series_catalog'::regclass,
              'macro_observations'::regclass
          )
        """
    )
    pairs = {(str(row["source_table"]), str(row["target_table"])) for row in rows}

    assert ("macro_series_catalog", "ops_data_sources") in pairs
    assert ("macro_observations", "macro_series_catalog") in pairs
    assert ("macro_observations", "ops_data_sources") in pairs
    assert ("macro_observations", "ops_ingestion_runs") in pairs


async def test_macro_observations_require_provenance_and_json_objects(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(NotNullViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO macro_observations(series_code, ref_ts, revision, value)
            VALUES('ipca', '2026-01-01'::timestamptz, 0, 0.42)
            """
        )

    run_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('bcb_sgs', 'finlib-macro-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO macro_observations(
                series_code, ref_ts, revision, value, source_id, run_id,
                lineage_hash, quality_flags
            )
            VALUES(
                'ipca', '2026-01-01'::timestamptz, 0, 0.42, 'bcb_sgs', $1,
                'sha256:bad-quality-flags', '[]'::jsonb
            )
            """,
            run_id,
        )

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            """
            INSERT INTO macro_observations(
                series_code, ref_ts, revision, value, source_id, run_id,
                lineage_hash, metadata
            )
            VALUES(
                'ipca', '2026-01-01'::timestamptz, 0, 0.42, 'bcb_sgs', $1,
                'sha256:bad-metadata', '[]'::jsonb
            )
            """,
            run_id,
        )


@pytest.mark.parametrize(
    ("field_name", "sql_value"),
    (
        pytest.param("display_name", "E'\\t'", id="tab-display-name"),
        pytest.param("provider", "E'\\n'", id="newline-provider"),
        pytest.param("provider_code", "E'\\r'", id="carriage-provider-code"),
        pytest.param("methodology_note", "'   '", id="space-methodology-note"),
    ),
)
async def test_macro_catalog_rejects_whitespace_only_required_text(
    postgres_client: PostgresClient,
    field_name: str,
    sql_value: str,
) -> None:
    await _migrate(postgres_client)

    values = {
        "display_name": "'Synthetic'",
        "provider": "'bcb_sgs'",
        "provider_code": "'999999'",
        "methodology_note": "'Synthetic planning reference'",
    }
    values[field_name] = sql_value

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            f"""
            INSERT INTO macro_series_catalog(
                series_code, display_name, provider, provider_code,
                provider_code_status, source_id, unit, periodicity, value_type,
                methodology_note, requires_live_verification
            )
            VALUES(
                'synthetic_{field_name}', {values["display_name"]},
                {values["provider"]}, {values["provider_code"]},
                'planning_reference', 'bcb_sgs', 'percent', 'monthly',
                'rate_percent', {values["methodology_note"]}, true
            )
            """
        )


@pytest.mark.parametrize(
    "sql_value",
    ("E'\\t'", "E'\\n'", "E'\\r'", "'   '"),
)
async def test_macro_observations_reject_whitespace_only_lineage_hash(
    postgres_client: PostgresClient,
    sql_value: str,
) -> None:
    await _migrate(postgres_client)
    run_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('bcb_sgs', 'finlib-macro-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )

    with pytest.raises(CheckViolationError):
        await postgres_client.pool.execute(
            f"""
            INSERT INTO macro_observations(
                series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
            )
            VALUES(
                'ipca', '2026-01-01'::timestamptz, 0, 0.42,
                'bcb_sgs', $1, {sql_value}
            )
            """,
            run_id,
        )
