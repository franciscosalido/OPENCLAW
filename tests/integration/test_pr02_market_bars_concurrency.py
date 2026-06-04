from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
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
async def repo_client() -> AsyncGenerator[tuple[PostgresClient, FinanceRepository], None]:
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


async def test_market_calendar_close_at_lte_open_at_real(
    repo_client: tuple[PostgresClient, FinanceRepository],
) -> None:
    client, _ = repo_client
    now = datetime(2026, 6, 4, 10, tzinfo=UTC)

    with pytest.raises(asyncpg.CheckViolationError):
        await client.pool.execute(
            """
            INSERT INTO market_calendars(exchange, session_date, is_open, open_at, close_at)
            VALUES($1, $2, TRUE, $3, $3)
            """,
            f"TEST-{uuid4().hex[:8]}",
            date(2026, 6, 4),
            now,
        )


async def test_concurrent_market_bar_upsert_same_key_real(
    repo_client: tuple[PostgresClient, FinanceRepository],
) -> None:
    client, repository = repo_client
    instrument = await repository.create_market_instrument(
        symbol=f"SAMEKEY-{uuid4().hex[:8]}",
        exchange="NASDAQ",
        asset_class="equity",
    )
    ts = datetime(2026, 7, 1, tzinfo=UTC)

    async def upsert(offset: int) -> MarketBar:
        return await repository.upsert_market_bar(
            MarketBar(
                ts=ts,
                instrument_id=instrument.instrument_id,
                timeframe="1d",
                open=10.0 + offset,
                high=12.0 + offset,
                low=9.0 + offset,
                close=11.0 + offset,
                volume=100.0 + offset,
                source_id="synthetic",
                ingested_at=ts,
                schema_version="market-bar-v1",
            )
        )

    await asyncio.gather(*(upsert(i) for i in range(50)))
    count = await client.pool.fetchval(
        """
        SELECT count(*)
        FROM market_bars
        WHERE instrument_id = $1 AND timeframe = '1d' AND ts = $2
        """,
        instrument.instrument_id,
        ts,
    )

    assert count == 1
