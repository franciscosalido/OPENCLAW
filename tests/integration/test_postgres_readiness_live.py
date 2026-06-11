from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations
from scripts.check_postgres_readiness import (
    DEFAULT_READONLY_ROLE,
    PostgresReadinessConfig,
    REQUIRED_EXTENSIONS,
    readiness_ok,
    run_readiness,
)
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


async def test_postgres_readiness_live_after_migrations(
    postgres_client: PostgresClient,
) -> None:
    base_dsn = _test_dsn()
    if base_dsn is None:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")

    await _require_extension_controls(postgres_client)
    await run_migrations(postgres_client)
    # pg_stat_statements requires shared_preload_libraries in the server
    # config. The local compose configures that; this only installs the SQL
    # objects inside the isolated database.
    await postgres_client.pool.execute(
        "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"
    )

    database = await postgres_client.pool.fetchval("SELECT current_database()")
    assert isinstance(database, str)

    config = PostgresReadinessConfig(
        dsn=database_dsn(base_dsn, database),
        expected_database=database,
        readonly_role=DEFAULT_READONLY_ROLE,
    )
    report = await run_readiness(config)

    assert readiness_ok(report), (
        f"PostgreSQL readiness gate failed: {report}. "
        "If readonly_role is fail on an existing local volume, apply "
        "infra/postgres/initdb/002_readonly_role.sql once. "
        "If pg_stat_statements is fail, create the extension in the target "
        "database after confirming shared_preload_libraries includes it."
    )
    assert report["migration_head"] == "ok"
    assert report["pg_trgm"] == "ok"
    assert report["btree_gin"] == "ok"


async def _require_extension_controls(client: PostgresClient) -> None:
    available = await client.pool.fetch(
        """
        SELECT name
        FROM pg_available_extensions
        WHERE name = ANY($1::text[])
        """,
        list(REQUIRED_EXTENSIONS),
    )
    available_names = {row["name"] for row in available}
    missing = set(REQUIRED_EXTENSIONS) - available_names
    if missing:
        pytest.skip(f"Postgres extension controls unavailable: {sorted(missing)}")
