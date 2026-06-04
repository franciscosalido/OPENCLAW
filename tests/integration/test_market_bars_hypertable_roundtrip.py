from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.finance_models import MarketBar
from backend.temporal.finance_repository import FinanceRepository
from backend.temporal.timescale import is_timescale_available


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def repository() -> AsyncGenerator[FinanceRepository, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    client = await PostgresClient.create(dsn=dsn)
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for PR-02 integration tests")
    await run_migrations(client)
    try:
        yield FinanceRepository(client)
    finally:
        await client.close()


async def test_market_bars_window_roundtrip_and_upsert(repository: FinanceRepository) -> None:
    instrument = await repository.create_market_instrument(
        symbol=f"AAPL-{uuid4().hex[:8]}",
        exchange="NASDAQ",
        asset_class="equity",
        metadata={"unicode": "ação"},
    )
    base_ts = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [
        MarketBar(
            ts=base_ts + timedelta(days=i),
            instrument_id=instrument.instrument_id,
            timeframe="1d",
            open=10.0 + i,
            high=12.0 + i,
            low=9.0 + i,
            close=11.0 + i,
            volume=100.0 + i,
            amount=1000.0 + i,
            factor=1.0,
            source_id="synthetic",
            ingested_at=base_ts,
            schema_version="market-bar-v1",
            quality_flags={"invalid": False, "nested": {"i": i}},
            metadata={"bar": i},
        )
        for i in range(3)
    ]
    assert await repository.upsert_market_bars(bars) == 3
    assert await repository.upsert_market_bars([bars[0]]) == 1

    fetched = await repository.get_market_bars_window(
        instrument_id=instrument.instrument_id,
        timeframe="1d",
        ascending=True,
    )
    descending = await repository.get_market_bars_window(
        instrument_id=instrument.instrument_id,
        timeframe="1d",
        ascending=False,
        limit=2,
    )

    assert [bar.ts for bar in fetched] == sorted(bar.ts for bar in fetched)
    assert len(fetched) == 3
    assert len(descending) == 2
    assert fetched[0].ts.tzinfo is not None
    assert fetched[0].quality_flags["nested"] == {"i": 0}


async def test_same_symbol_different_exchange_is_allowed(repository: FinanceRepository) -> None:
    symbol = f"AAPL-{uuid4().hex[:8]}"
    first = await repository.create_market_instrument(
        symbol=symbol,
        exchange="NASDAQ",
        asset_class="equity",
    )
    second = await repository.create_market_instrument(
        symbol=symbol,
        exchange="TEST_EXCHANGE",
        asset_class="equity",
    )

    assert first.instrument_id != second.instrument_id
