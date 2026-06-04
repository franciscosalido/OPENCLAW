from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

from backend.memory.postgres.client import PostgresClient
from backend.memory.postgres.migrations import run_migrations


pytestmark = pytest.mark.integration


def _test_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")


@pytest.fixture
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    client = await PostgresClient.create(dsn=dsn)
    try:
        yield client
    finally:
        await client.close()


async def test_migrations_apply_once(postgres_client: PostgresClient) -> None:
    applied = await run_migrations(postgres_client)

    assert applied


async def test_migrations_apply_twice_idempotent(postgres_client: PostgresClient) -> None:
    await run_migrations(postgres_client)
    applied = await run_migrations(postgres_client)

    assert applied == ()


async def test_schema_migrations_records_checksums(postgres_client: PostgresClient) -> None:
    await run_migrations(postgres_client)
    rows = await postgres_client.pool.fetch(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    )

    assert rows
    assert all(len(row["checksum"]) == 64 for row in rows)


async def test_required_indexes_exist_in_db(postgres_client: PostgresClient) -> None:
    await run_migrations(postgres_client)
    rows = await postgres_client.pool.fetch(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    )
    names = {row["indexname"] for row in rows}
    required = {
        "idx_sessions_agent_id",
        "idx_sessions_created_at",
        "idx_sessions_agent_created_at",
        "idx_sessions_user_id",
        "idx_turns_session_id",
        "idx_turns_created_at",
        "idx_turns_session_created_at",
        "idx_agent_states_agent_id",
        "idx_agent_states_session_id",
        "idx_agent_states_updated_at",
        "idx_agent_states_agent_session",
        "idx_entity_mentions_turn_id",
        "idx_entity_mentions_entity_text",
        "idx_entity_mentions_entity_type",
    }

    assert required <= names
