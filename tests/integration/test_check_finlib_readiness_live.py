from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from io import StringIO

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from backend.temporal.timescale import is_timescale_available
from scripts import check_finlib_readiness
from tests.integration.postgres_isolated_db import (
    database_dsn,
    isolated_postgres_client,
)


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    async with isolated_postgres_client(dsn, prefix="finlib_readiness") as client:
        yield client


async def _migrate(client: PostgresClient) -> None:
    async with client.pool.acquire() as conn:
        if not await is_timescale_available(conn):
            pytest.skip("TimescaleDB extension is required")
    await run_migrations(client)


async def test_finlib_readiness_live_is_ready_and_idempotent(
    postgres_client: PostgresClient,
) -> None:
    base_dsn = _test_dsn()
    if base_dsn is None:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    await _migrate(postgres_client)
    database = await postgres_client.pool.fetchval("SELECT current_database()")
    dsn = database_dsn(base_dsn, str(database))

    first_stdout = StringIO()
    first_code = check_finlib_readiness.main(
        ["--json"],
        env={"TEST_POSTGRES_DSN": dsn},
        stdout=first_stdout,
    )
    first_report = json.loads(first_stdout.getvalue())
    second_stdout = StringIO()
    second_code = check_finlib_readiness.main(
        ["--json"],
        env={"TEST_POSTGRES_DSN": dsn},
        stdout=second_stdout,
    )
    second_report = json.loads(second_stdout.getvalue())

    assert first_code == 0
    assert second_code == 0
    assert first_report["status"] == "READY"
    assert second_report["ready_for_data_agents"] is True
    assert first_report["migration_head"] == "ok"
    assert first_report["compression"]["destructive_retention"] == "ok"
    assert first_report["kronos_input_ready"]["status"] in {"ok", "degraded"}
    assert first_report["failed_checks"] == []


async def test_finlib_readiness_live_blocks_missing_critical_table(
    postgres_client: PostgresClient,
) -> None:
    await _migrate(postgres_client)
    await postgres_client.pool.execute("DROP TABLE audit_agent_writes")

    report = await check_finlib_readiness.build_readiness_report(
        postgres_client.pool,
        check_finlib_readiness.FinlibReadinessConfig(
            dsn="postgresql://redacted",
            timeout_seconds=1,
        ),
    )

    assert report["status"] == "BLOCKED"
    failed_checks = report["failed_checks"]
    assert isinstance(failed_checks, list)
    assert "schemas.audit" in failed_checks
