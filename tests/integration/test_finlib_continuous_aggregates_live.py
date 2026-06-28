from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_closeout") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required")
    await run_migrations(client)


async def test_finlib_closeout_views_and_cagg_roundtrip(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    source_id = f"closeout_source_{uuid4().hex}"
    run_id = uuid4()
    trace_id = uuid4()
    instrument_id = uuid4()
    bond_id = uuid4()
    fund_cnpj = "00000000000100"

    await postgres_client.pool.execute(
        """
        INSERT INTO ops_data_sources(source_id, kind, methodology_limitations)
        VALUES($1, 'internal', 'synthetic closeout integration source')
        """,
        source_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO ops_ingestion_runs(run_id, source_id, agent_id, mode, status, trace_id)
        VALUES($1, $2, 'closeout-test', 'dry_run', 'created', $3)
        """,
        run_id,
        source_id,
        trace_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO macro_series_catalog(
            series_code, display_name, provider, provider_code, source_id,
            unit, periodicity, value_type, methodology_note
        )
        VALUES('closeout_ipca', 'Closeout IPCA', 'internal', '1', $1,
               'percent', 'monthly', 'rate_percent', 'synthetic')
        """,
        source_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO macro_observations(
            series_code, ref_ts, revision, value, source_id, run_id, lineage_hash
        )
        VALUES
            ('closeout_ipca', '2026-01-01T00:00:00Z', 0, 0.42, $1, $2, 'sha256:macro0'),
            ('closeout_ipca', '2026-01-01T00:00:00Z', 1, 0.43, $1, $2, 'sha256:macro1')
        """,
        source_id,
        run_id,
    )
    latest_macro = await postgres_client.pool.fetchval(
        """
        SELECT value
        FROM macro_observations_latest_revision
        WHERE series_code = 'closeout_ipca'
        """
    )
    assert str(latest_macro) == "0.43"

    await postgres_client.pool.execute(
        """
        INSERT INTO treasury_bonds(bond_id, bond_type, maturity_date, display_name, source_id)
        VALUES($1, 'Tesouro_Selic', '2029-03-01', 'Tesouro Selic 2029', $2)
        """,
        bond_id,
        source_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO treasury_prices(
            bond_id, ts, price_bid, price_ask, source_id, run_id, lineage_hash
        )
        VALUES
            ($1, '2026-01-01T00:00:00Z', 1000, 1001, $2, $3, 'sha256:treasury0'),
            ($1, '2026-01-02T00:00:00Z', 1002, 1003, $2, $3, 'sha256:treasury1')
        """,
        bond_id,
        source_id,
        run_id,
    )
    latest_treasury_ts = await postgres_client.pool.fetchval(
        "SELECT ts FROM treasury_latest_prices_view WHERE bond_id = $1",
        bond_id,
    )
    assert latest_treasury_ts == datetime(2026, 1, 2, tzinfo=timezone.utc)

    await postgres_client.pool.execute(
        """
        INSERT INTO fund_registry(fund_cnpj, legal_name, status, source_id)
        VALUES($1, 'Synthetic Fund', 'active', $2)
        """,
        fund_cnpj,
        source_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO fund_daily_info(
            fund_cnpj, ts, revision, quota_value, net_worth, shareholders,
            source_id, run_id, lineage_hash
        )
        VALUES
            ($1, '2026-01-02T00:00:00Z', 0, 10, 1000, 10, $2, $3, 'sha256:fund0'),
            ($1, '2026-01-02T00:00:00Z', 1, 11, 1100, 10, $2, $3, 'sha256:fund1'),
            ($1, '2026-01-31T00:00:00Z', 0, 12, 1200, 10, $2, $3, 'sha256:fund2')
        """,
        fund_cnpj,
        source_id,
        run_id,
    )
    latest_quota = await postgres_client.pool.fetchval(
        """
        SELECT quota_value
        FROM fund_daily_info_latest_revision
        WHERE fund_cnpj = $1 AND ts = '2026-01-02T00:00:00Z'
        """,
        fund_cnpj,
    )
    assert str(latest_quota) == "11"
    monthly_return = await postgres_client.pool.fetchval(
        "SELECT monthly_return FROM fund_monthly_quota_returns WHERE fund_cnpj = $1",
        fund_cnpj,
    )
    assert str(monthly_return).startswith("0.0909")

    await postgres_client.pool.execute(
        """
        INSERT INTO market_instruments(instrument_id, symbol, exchange, asset_class)
        VALUES($1, 'CLOSE3', 'B3', 'stock')
        """,
        instrument_id,
    )
    await postgres_client.pool.execute(
        """
        INSERT INTO market_bars(
            instrument_id, ts, timeframe, open, high, low, close, volume, amount,
            source_id
        )
        VALUES
            ($1, '2026-01-05T10:00:00Z', '1h', 10, 12, 9, 11, 100, 1000, $2),
            ($1, '2026-01-05T11:00:00Z', '1h', 11, 13, 10, 12, 150, 1800, $2)
        """,
        instrument_id,
        source_id,
    )
    await postgres_client.pool.execute(
        "CALL refresh_continuous_aggregate('market_bars_1d_cagg', NULL, NULL)"
    )
    market_row = await postgres_client.pool.fetchrow(
        "SELECT open, high, low, close, volume, amount FROM market_bars_1d"
    )
    assert market_row is not None
    assert float(market_row["open"]) == 10.0
    assert float(market_row["high"]) == 13.0
    assert float(market_row["low"]) == 9.0
    assert float(market_row["close"]) == 12.0
    assert float(market_row["volume"]) == 250.0
    assert float(market_row["amount"]) == 2800.0

    cagg_exists = await postgres_client.pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM timescaledb_information.continuous_aggregates
            WHERE view_name = 'market_bars_1d_cagg'
        )
        """
    )
    assert cagg_exists is True
    retention_jobs = await postgres_client.pool.fetchval(
        """
        SELECT count(*)
        FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_retention'
           OR proc_name = 'drop_chunks'
        """
    )
    assert retention_jobs == 0
