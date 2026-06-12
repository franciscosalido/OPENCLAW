from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Mapping, Sequence
from time import monotonic
from typing import Any, Protocol, cast
from uuid import UUID

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

EMPTY_OUTBOX_TARGET_SECONDS = 0.005
POLL_QUERY = """
SELECT event_id
FROM ops_outbox_events
WHERE status = 'pending'
  AND next_attempt_at <= now()
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT $1
"""


class FetchConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, Any]]:
        """Fetch rows from an asyncpg connection or pool proxy."""
        ...


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_outbox") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB outbox tests")
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
        VALUES('b3_cotacoes_historicas', 'finlib-outbox-test', 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """
    )
    return UUID(str(run_id))


async def _insert_event(
    client: PostgresClient,
    *,
    run_id: UUID,
    aggregate_id: str,
    status: str = "pending",
    next_attempt: str = "now()",
) -> UUID:
    event_id = await client.pool.fetchval(
        f"""
        INSERT INTO ops_outbox_events(
            event_type, aggregate_type, aggregate_id, status, next_attempt_at, run_id
        )
        VALUES('finlib.test', 'ingestion_run', $1, $2, {next_attempt}, $3)
        RETURNING event_id
        """,
        aggregate_id,
        status,
        run_id,
    )
    return UUID(str(event_id))


async def _poll_locked(
    connection: FetchConnection,
    *,
    limit: int,
) -> set[UUID]:
    rows = await connection.fetch(POLL_QUERY, limit)
    return {UUID(str(row["event_id"])) for row in rows}


async def test_outbox_skip_locked_prevents_double_dispatch(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    expected = {
        await _insert_event(postgres_client, run_id=run_id, aggregate_id=f"event-{i}")
        for i in range(3)
    }

    first_conn = await postgres_client.pool.acquire()
    second_conn = await postgres_client.pool.acquire()
    try:
        first_tx = first_conn.transaction()
        second_tx = second_conn.transaction()
        await first_tx.start()
        first_ids = await _poll_locked(cast("FetchConnection", first_conn), limit=2)
        await second_tx.start()
        second_ids = await _poll_locked(cast("FetchConnection", second_conn), limit=2)

        assert first_ids
        assert second_ids
        assert first_ids.isdisjoint(second_ids)
        assert first_ids | second_ids == expected
    finally:
        await second_tx.rollback()
        await first_tx.rollback()
        await postgres_client.pool.release(second_conn)
        await postgres_client.pool.release(first_conn)


async def test_outbox_poll_filters_future_and_non_pending_events(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)
    ready = await _insert_event(postgres_client, run_id=run_id, aggregate_id="ready")
    future = await _insert_event(
        postgres_client,
        run_id=run_id,
        aggregate_id="future",
        next_attempt="now() + interval '1 hour'",
    )
    completed = await _insert_event(
        postgres_client,
        run_id=run_id,
        aggregate_id="completed",
        status="completed",
    )

    async with postgres_client.pool.acquire() as conn:
        async with conn.transaction():
            ids = await _poll_locked(cast("FetchConnection", conn), limit=10)

    assert ready in ids
    assert future not in ids
    assert completed not in ids


async def test_empty_outbox_poll_meets_local_latency_target(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    samples: list[float] = []
    async with postgres_client.pool.acquire() as conn:
        for _ in range(6):
            start = monotonic()
            rows = await conn.fetch(POLL_QUERY, 10)
            elapsed = monotonic() - start
            assert rows == []
            samples.append(elapsed)

    assert min(samples[1:]) < EMPTY_OUTBOX_TARGET_SECONDS


async def test_outbox_pending_partial_index_exists(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    row = await postgres_client.pool.fetchrow(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'ops_outbox_events'
          AND indexname = 'idx_ops_outbox_pending'
        """
    )

    assert row is not None
    indexdef = str(row["indexdef"])
    assert "next_attempt_at" in indexdef
    assert "created_at" in indexdef
    assert "WHERE (status = 'pending'::text)" in indexdef


async def test_data_quality_checks_accept_expected_severities(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    run_id = await _create_run(postgres_client)

    for severity in ("info", "warning", "error", "critical"):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_quality_checks(
                run_id, check_name, target_table, severity, passed, observed, expected
            )
            VALUES($1, $2, 'ops_ingestion_runs', $3, true, '{}'::jsonb, '{}'::jsonb)
            """,
            run_id,
            f"check-{severity}",
            severity,
        )

    count = await postgres_client.pool.fetchval(
        "SELECT count(*) FROM ops_data_quality_checks WHERE run_id = $1",
        run_id,
    )
    assert count == 4

    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_quality_checks(
                run_id, check_name, target_table, severity, passed
            )
            VALUES($1, 'bad-severity', 'ops_ingestion_runs', 'fatal', false)
            """,
            run_id,
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_quality_checks(
                run_id, check_name, target_table, severity, passed, observed
            )
            VALUES($1, 'bad-json', 'ops_ingestion_runs', 'error', false, '[]'::jsonb)
            """,
            run_id,
        )
