from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from tests.integration.postgres_isolated_db import isolated_postgres_client


pytestmark = pytest.mark.integration

INVALID_INGESTION_RUN_STATEMENTS = (
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('missing_source', 'agent', 'dry_run', 'created', uuidv7())
        """,
        id="missing-source-fk",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'agent', 'invalid', 'created', uuidv7())
        """,
        id="invalid-mode",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'invalid', uuidv7())
        """,
        id="invalid-status",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, records_seen, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'created', -1, uuidv7())
        """,
        id="negative-records-seen",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, started_at, finished_at, trace_id
        )
        VALUES(
            'b3_cotacoes_historicas', 'agent', 'dry_run', 'completed',
            '2026-01-02'::timestamptz, '2026-01-01'::timestamptz, uuidv7()
        )
        """,
        id="finished-before-started",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'agent', 'execute', 'completed', uuidv7())
        """,
        id="execute-completed-missing-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'execute', 'completed', ' ', uuidv7())
        """,
        id="execute-completed-blank-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', '   ', 'dry_run', 'created', uuidv7())
        """,
        id="blank-agent-id",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', E'\\t', 'dry_run', 'created', uuidv7())
        """,
        id="tab-agent-id",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', E'\\n', 'dry_run', 'created', uuidv7())
        """,
        id="newline-agent-id",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', E'\\r', 'dry_run', 'created', uuidv7())
        """,
        id="carriage-return-agent-id",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'created', NULL)
        """,
        id="null-trace-id",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, metadata
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'created', uuidv7(), '[]'::jsonb)
        """,
        id="metadata-array",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'execute', 'completed', E'\\t', uuidv7())
        """,
        id="execute-completed-tab-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'execute', 'completed', E'\\n', uuidv7())
        """,
        id="execute-completed-newline-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'execute', 'completed', E'\\r', uuidv7())
        """,
        id="execute-completed-carriage-return-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'created', E'\\t', uuidv7())
        """,
        id="dry-run-tab-snapshot",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, error_summary
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'failed', uuidv7(), E'\\t')
        """,
        id="tab-error-summary",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, error_summary
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'failed', uuidv7(), E'\\n')
        """,
        id="newline-error-summary",
    ),
    pytest.param(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, trace_id, error_summary
        )
        VALUES('b3_cotacoes_historicas', 'agent', 'dry_run', 'failed', uuidv7(), E'\\r')
        """,
        id="carriage-return-error-summary",
    ),
)


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_ops") as client:
        yield client


async def _require_timescale_and_uuidv7(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required for FINLIB ops tests")
    try:
        version = await client.pool.fetchval("SELECT uuid_extract_version(uuidv7())")
    except Exception as exc:
        raise AssertionError("PostgreSQL 18 uuidv7() is required") from exc
    assert version == 7


async def _migrate(client: PostgresClient) -> None:
    await _require_timescale_and_uuidv7(client)
    await run_migrations(client)


async def test_finlib_ops_migration_applies_idempotently(
    postgres_client: PostgresClient,
) -> None:
    await _require_timescale_and_uuidv7(postgres_client)
    first = await run_migrations(postgres_client)
    second = await run_migrations(postgres_client)

    assert "019_create_ops_sources_runs" in first
    assert second == ()


async def test_finlib_ops_tables_and_b3_seed_exist(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    sources_table = await postgres_client.pool.fetchval(
        "SELECT to_regclass('public.ops_data_sources')"
    )
    runs_table = await postgres_client.pool.fetchval(
        "SELECT to_regclass('public.ops_ingestion_runs')"
    )
    b3 = await postgres_client.pool.fetchrow(
        "SELECT * FROM ops_data_sources WHERE source_id = $1",
        "b3_cotacoes_historicas",
    )

    assert sources_table == "ops_data_sources"
    assert runs_table == "ops_ingestion_runs"
    assert b3 is not None
    assert b3["kind"] == "exchange"
    assert b3["enabled"] is True
    assert "sem ajuste por inflação" in b3["methodology_limitations"]
    assert b3["metadata"]["country"] == "BR"
    assert b3["metadata"]["source_family"] == "historical_quotes"


async def test_finlib_ops_positive_runs_and_uuidv7_default(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    dry_run_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(source_id, agent_id, mode, status, trace_id)
        VALUES($1, $2, 'dry_run', 'created', uuidv7())
        RETURNING run_id
        """,
        "b3_cotacoes_historicas",
        "finlib-test-agent",
    )
    execute_id = await postgres_client.pool.fetchval(
        """
        INSERT INTO ops_ingestion_runs(
            source_id, agent_id, mode, status, source_snapshot_hash, trace_id
        )
        VALUES($1, $2, 'execute', 'completed', $3, uuidv7())
        RETURNING run_id
        """,
        "b3_cotacoes_historicas",
        "finlib-test-agent",
        "sha256:synthetic-fixture",
    )

    assert (
        await postgres_client.pool.fetchval(
            "SELECT uuid_extract_version($1::uuid)",
            dry_run_id,
        )
        == 7
    )
    assert (
        await postgres_client.pool.fetchval(
            "SELECT uuid_extract_version($1::uuid)",
            execute_id,
        )
        == 7
    )


async def test_finlib_ops_sources_constraints_are_enforced(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_sources(
                source_id, kind, methodology_limitations, metadata
            )
            VALUES($1, 'exchange', 'valid limitation', '{}'::jsonb)
            """,
            "INVALID SOURCE",
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_sources(source_id, kind, methodology_limitations)
            VALUES('blank_limit', 'exchange', '   ')
            """
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_sources(
                source_id, kind, methodology_limitations, metadata
            )
            VALUES('array_metadata', 'exchange', 'valid limitation', '[]'::jsonb)
            """
        )
    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_sources(source_id, kind, methodology_limitations)
            VALUES($1, 'exchange', 'valid limitation')
            """,
            "a" * 129,
        )


@pytest.mark.parametrize(
    ("source_id", "methodology_limitations"),
    (
        pytest.param("tab_limit", "\t", id="tab-methodology-limitations"),
        pytest.param("newline_limit", "\n", id="newline-methodology-limitations"),
        pytest.param(
            "carriage_return_limit",
            "\r",
            id="carriage-return-methodology-limitations",
        ),
    ),
)
async def test_finlib_ops_sources_reject_whitespace_only_methodology_limitations(
    postgres_client: PostgresClient,
    source_id: str,
    methodology_limitations: str,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(Exception):
        await postgres_client.pool.execute(
            """
            INSERT INTO ops_data_sources(source_id, kind, methodology_limitations)
            VALUES($1, 'exchange', $2)
            """,
            source_id,
            methodology_limitations,
        )


@pytest.mark.parametrize("statement", INVALID_INGESTION_RUN_STATEMENTS)
async def test_finlib_ops_ingestion_run_constraints_are_enforced(
    postgres_client: PostgresClient,
    statement: str,
) -> None:
    await _migrate(postgres_client)

    with pytest.raises(Exception):
        await postgres_client.pool.execute(statement)
