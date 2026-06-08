from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.finance_models import (
    KronosForecast,
    MarketBar,
    MarketFeature,
    ModelRun,
    QlibProjectionManifest,
)
from backend.temporal.finance_repository import FinanceRepository
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def repo_client() -> AsyncGenerator[tuple[PostgresClient, FinanceRepository], None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")

    async with isolated_postgres_client(dsn, prefix="finance_repository") as client:
        async with client.pool.acquire() as conn:
            if not await is_timescale_available(conn):
                pytest.skip("TimescaleDB extension is required for PR-02 integration tests")
        await run_migrations(client)
        await _reset_roundtrip_state(client)
        yield client, FinanceRepository(client)


async def _reset_roundtrip_state(client: PostgresClient) -> None:
    # This test runs in an isolated database; CASCADE is intentionally scoped to
    # disposable test state and keeps repeated live attempts deterministic.
    await client.pool.execute("TRUNCATE TABLE qlib_projection_manifests CASCADE")


async def test_finance_repository_full_roundtrip(
    repo_client: tuple[PostgresClient, FinanceRepository],
) -> None:
    client, repository = repo_client
    now = datetime(2026, 6, 4, tzinfo=UTC)
    symbol = f"DROP-TABLE-{uuid4().hex[:8]};--"
    instrument = await repository.create_market_instrument(
        symbol=symbol,
        exchange="UNICODE-測試",
        asset_class="equity",
        metadata={"payload": "Robert'); DROP TABLE market_instruments;--"},
    )
    fetched = await repository.get_market_instrument(instrument.instrument_id)
    by_symbol = await repository.get_market_instrument_by_symbol(
        symbol=symbol,
        exchange="UNICODE-測試",
    )
    upserted = await repository.upsert_market_instrument(
        symbol=symbol,
        exchange="UNICODE-測試",
        asset_class="equity",
        currency="USD",
    )

    assert fetched == instrument
    assert by_symbol == instrument
    assert upserted.instrument_id == instrument.instrument_id

    bar = MarketBar(
        ts=now,
        instrument_id=instrument.instrument_id,
        timeframe="1d",
        open=10.0,
        high=12.0,
        low=9.0,
        close=11.0,
        volume=100.0,
        amount=1000.0,
        factor=1.0,
        source_id="source'); DROP TABLE market_bars;--",
        ingested_at=now,
        schema_version="market-bar-v1",
        quality_flags={"invalid": False},
        metadata={"unicode": "ação"},
    )
    await repository.upsert_market_bar(bar)
    assert await repository.upsert_market_bars([bar]) == 1
    assert len(await repository.get_market_bars_window(instrument_id=instrument.instrument_id, timeframe="1d")) == 1

    feature = await repository.insert_market_feature(
        MarketFeature(
            ts=now,
            instrument_id=instrument.instrument_id,
            timeframe="1d",
            feature_name="return_1d",
            feature_value=0.01,
            feature_version="feature-v1",
            source_id="synthetic",
            ingested_at=now,
            schema_version="market-feature-v1",
            metadata={},
        )
    )
    assert feature.feature_name == "return_1d"

    run = await repository.create_model_run(
        ModelRun(
            run_id=uuid4(),
            model_name="kronos",
            model_version="contract-v1",
            adapter_name="quimera",
            adapter_version="adapter-v1",
            input_start_ts=now - timedelta(days=10),
            input_end_ts=now,
            created_at=now,
            source_id="synthetic",
            ingested_at=now,
            schema_version="model-run-v1",
            params={"lookback": 10},
            metrics={},
            metadata={},
        )
    )
    forecast = await repository.insert_kronos_forecast(
        KronosForecast(
            forecast_ts=now + timedelta(days=1),
            run_id=run.run_id,
            instrument_id=instrument.instrument_id,
            timeframe="1d",
            horizon_step=1,
            close_pred=12.5,
            quantiles={"0.5": 12.5},
            sample_count=1,
            source_id="synthetic",
            ingested_at=now,
            schema_version="kronos-forecast-v1",
            metadata={},
            created_at=now,
        )
    )
    latest = await repository.get_latest_kronos_forecast(
        instrument_id=instrument.instrument_id,
        timeframe="1d",
    )
    assert latest == forecast

    manifest = await repository.create_qlib_projection_manifest(
        QlibProjectionManifest(
            projection_id=uuid4(),
            projection_name="daily-bars",
            projection_version="projection-v1",
            format="pandas",
            source_query_hash="query",
            transform_hash="transform",
            row_count=1,
            start_ts=now,
            end_ts=now,
            source_id="synthetic",
            ingested_at=now,
            schema_version="qlib-projection-manifest-v1",
            metadata={"unicode": "測試"},
            created_at=now,
        )
    )
    fetched_manifest = await repository.get_qlib_projection_manifest(manifest.projection_id)
    assert fetched_manifest == manifest

    await client.pool.execute(
        "DELETE FROM market_instruments WHERE instrument_id = $1",
        instrument.instrument_id,
    )
    bar_count = await client.pool.fetchval(
        "SELECT count(*) FROM market_bars WHERE instrument_id = $1",
        instrument.instrument_id,
    )
    forecast_count = await client.pool.fetchval(
        "SELECT count(*) FROM kronos_forecasts WHERE instrument_id = $1",
        instrument.instrument_id,
    )
    assert bar_count == 0
    assert forecast_count == 0
