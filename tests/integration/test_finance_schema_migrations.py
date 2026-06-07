from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

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
    async with isolated_postgres_client(dsn, prefix="finance_migrations") as client:
        yield client


async def _require_timescale(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for PR-02 integration tests")


async def _require_uuidv7(client: PostgresClient) -> None:
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError(
            "PostgreSQL 18 uuidv7() is required for PR-02 finance migrations"
        ) from exc
    assert version == 7


async def test_finance_migrations_apply_twice_and_register_checksums(
    postgres_client: PostgresClient,
) -> None:
    await _require_timescale(postgres_client)
    await _require_uuidv7(postgres_client)
    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)
    rows = await postgres_client.pool.fetch(
        "SELECT version, checksum FROM schema_migrations WHERE version >= '010' ORDER BY version"
    )

    expected_versions = {
        "010_create_market_instruments",
        "016_create_qlib_projection_manifests",
    }
    recorded_versions = {row["version"] for row in rows}
    first_finance_versions = {version for version in first if version >= "010"}

    assert first_finance_versions.issubset(recorded_versions)
    assert expected_versions <= recorded_versions
    assert second == ()
    assert len(rows) >= 7
    assert all(len(row["checksum"]) == 64 for row in rows)


async def test_finance_hypertables_and_uuidv7_available(postgres_client: PostgresClient) -> None:
    await _require_timescale(postgres_client)
    await _require_uuidv7(postgres_client)
    await run_migrations(postgres_client)
    async with postgres_client.pool.acquire() as conn:
        assert await is_hypertable(conn, "market_bars")
        assert await is_hypertable(conn, "market_features")
        assert await is_hypertable(conn, "kronos_forecasts")
    version = await postgres_client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    assert version == 7


async def test_finance_constraints_are_enforced(postgres_client: PostgresClient) -> None:
    await _require_timescale(postgres_client)
    await _require_uuidv7(postgres_client)
    await run_migrations(postgres_client)
    instrument_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO market_instruments(symbol, exchange, asset_class)
        VALUES($1, $2, $3)
        RETURNING instrument_id
        """,
        "AAPL",
        "NASDAQ",
        "equity",
    )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO market_instruments(symbol, exchange, asset_class)
            VALUES($1, $2, $3)
            """,
            "AAPL",
            "NASDAQ",
            "equity",
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO market_bars(ts, instrument_id, timeframe, open, high, low, close, source_id)
            VALUES(NOW(), $1, '1d', 10, 8, 9, 11, 'synthetic')
            """,
            instrument_id,
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO qlib_projection_manifests(
                projection_name, projection_version, format, source_query_hash, transform_hash
            )
            VALUES('x', 'v1', 'duckdb', 'q', 't')
            """
        )
