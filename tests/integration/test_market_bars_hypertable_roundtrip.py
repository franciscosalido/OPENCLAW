from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.finance_models import MarketBar
from backend.temporal.finance_models import MarketInstrument
from backend.temporal.finance_repository import FinanceRepository
from backend.temporal.timescale import is_timescale_available


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def repo_client() -> AsyncGenerator[
    tuple[PostgresClient, FinanceRepository], None
]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    client = await PostgresClient.create(dsn=dsn)
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for PR-02 integration tests")
    await run_migrations(client)
    try:
        yield client, FinanceRepository(client)
    finally:
        await client.close()


@pytest.fixture
def repository(
    repo_client: tuple[PostgresClient, FinanceRepository],
) -> FinanceRepository:
    return repo_client[1]


def _market_bar(
    *,
    instrument: MarketInstrument,
    ts: datetime,
    offset: int = 0,
) -> MarketBar:
    return MarketBar(
        ts=ts,
        instrument_id=instrument.instrument_id,
        timeframe="1d",
        open=10.0 + offset,
        high=12.0 + offset,
        low=9.0 + offset,
        close=11.0 + offset,
        volume=100.0 + offset,
        amount=1000.0 + offset,
        factor=1.0,
        source_id="synthetic",
        ingested_at=ts,
        schema_version="market-bar-v1",
        quality_flags={"invalid": False, "nested": {"i": offset}},
        metadata={"bar": offset},
    )


async def test_market_bars_window_roundtrip_and_upsert(
    repository: FinanceRepository,
) -> None:
    instrument = await repository.create_market_instrument(
        symbol=f"AAPL-{uuid4().hex[:8]}",
        exchange="NASDAQ",
        asset_class="equity",
        metadata={"unicode": "ação"},
    )
    base_ts = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [
        _market_bar(instrument=instrument, ts=base_ts + timedelta(days=i), offset=i)
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


async def test_same_symbol_different_exchange_is_allowed(
    repository: FinanceRepository,
) -> None:
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


async def test_concurrent_market_bar_upsert_50(
    repo_client: tuple[PostgresClient, FinanceRepository],
) -> None:
    client, repository = repo_client
    instrument = await repository.create_market_instrument(
        symbol=f"CONCURRENT-{uuid4().hex[:8]}",
        exchange="NASDAQ",
        asset_class="equity",
    )
    base_ts = datetime(2026, 7, 1, tzinfo=UTC)
    bars = [
        _market_bar(instrument=instrument, ts=base_ts + timedelta(minutes=i), offset=i)
        for i in range(50)
    ]

    await asyncio.gather(*(repository.upsert_market_bar(bar) for bar in bars))
    count = await client.pool.fetchval(
        "SELECT count(*) FROM market_bars WHERE instrument_id = $1",
        instrument.instrument_id,
    )

    assert count == 50
