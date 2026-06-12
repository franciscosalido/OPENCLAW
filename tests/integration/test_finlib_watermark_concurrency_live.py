from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

WATERMARK_UPSERT_SQL = """
INSERT INTO ops_ingestion_watermarks(
    source_id,
    dataset,
    watermark_value,
    watermark_ts,
    source_snapshot_hash,
    run_id
)
VALUES($1, $2, $3, $4::timestamptz, $5, $6)
ON CONFLICT (source_id, dataset) DO UPDATE SET
    watermark_value = excluded.watermark_value,
    watermark_ts = excluded.watermark_ts,
    source_snapshot_hash = excluded.source_snapshot_hash,
    run_id = excluded.run_id,
    updated_at = now()
WHERE ops_ingestion_watermarks.watermark_ts IS NULL
   OR (
       excluded.watermark_ts IS NOT NULL
       AND excluded.watermark_ts >= ops_ingestion_watermarks.watermark_ts
   )
RETURNING watermark_value, watermark_ts
"""


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_watermark") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB watermark tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7
    await run_migrations(client)


async def _create_run(client: PostgresClient) -> UUID:
    run_id = await client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'finlib-watermark-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _upsert_watermark(
    client: PostgresClient,
    *,
    run_id: UUID,
    value: str,
    timestamp: str,
) -> None:
    watermark_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    await client.pool.fetchrow(
        WATERMARK_UPSERT_SQL,
        "b3_cotacoes_historicas",
        "daily-bars",
        value,
        watermark_ts,
        f"sha256:{value}",
        run_id,
    )


async def test_concurrent_watermark_upsert_does_not_regress(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _upsert_watermark(
        postgres_client,
        run_id=run_id,
        value="2026-01-02",
        timestamp="2026-01-02T00:00:00Z",
    )

    await asyncio.gather(
        _upsert_watermark(
            postgres_client,
            run_id=run_id,
            value="2026-01-03",
            timestamp="2026-01-03T00:00:00Z",
        ),
        _upsert_watermark(
            postgres_client,
            run_id=run_id,
            value="2026-01-01",
            timestamp="2026-01-01T00:00:00Z",
        ),
    )

    row = await postgres_client.pool.fetchrow(
        """
        SELECT watermark_value, watermark_ts
        FROM ops_ingestion_watermarks
        WHERE source_id = 'b3_cotacoes_historicas'
          AND dataset = 'daily-bars'
        """
    )

    assert row is not None
    assert row["watermark_value"] == "2026-01-03"
    assert row["watermark_ts"].isoformat().startswith("2026-01-03")


async def test_direct_watermark_update_cannot_regress_timestamp(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    await _upsert_watermark(
        postgres_client,
        run_id=run_id,
        value="2026-01-02",
        timestamp="2026-01-02T00:00:00Z",
    )

    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            UPDATE ops_ingestion_watermarks
            SET watermark_value = '2026-01-01',
                watermark_ts = '2026-01-01T00:00:00Z'::timestamptz
            WHERE source_id = 'b3_cotacoes_historicas'
              AND dataset = 'daily-bars'
            """
        )


async def test_watermark_constraints_are_enforced(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    invalid_statements = (
        (
            """
            INSERT INTO ops_ingestion_watermarks(source_id, dataset, watermark_value)
            VALUES('b3_cotacoes_historicas', '   ', '2026-01-01')
            """,
            (),
        ),
        (
            """
            INSERT INTO ops_ingestion_watermarks(source_id, dataset, watermark_value)
            VALUES('b3_cotacoes_historicas', 'daily-bars', E'\\t')
            """,
            (),
        ),
        (
            """
            INSERT INTO ops_ingestion_watermarks(
                source_id, dataset, watermark_value, metadata
            )
            VALUES('b3_cotacoes_historicas', 'daily-bars', '2026-01-01', '[]'::jsonb)
            """,
            (),
        ),
        (
            """
            INSERT INTO ops_ingestion_watermarks(
                source_id, dataset, watermark_value, run_id
            )
            VALUES('missing_source', 'daily-bars', '2026-01-01', $1)
            """,
            (run_id,),
        ),
    )
    for statement, args in invalid_statements:
        with pytest.raises(Exception):
            await postgres_client.pool.execute(statement, *args)
