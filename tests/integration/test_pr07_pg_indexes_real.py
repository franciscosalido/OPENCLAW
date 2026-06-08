from __future__ import annotations

import os

import asyncpg  # type: ignore[import-untyped]
import pytest

pytestmark = pytest.mark.integration


async def test_required_memory_indexes_exist_in_real_db() -> None:
    dsn = os.getenv("TEST_POSTGRES_DSN") or os.getenv("QUIMERA_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN or QUIMERA_POSTGRES_DSN is required")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public'"
        )
    finally:
        await conn.close()
    names = {row["indexname"] for row in rows}

    for index_name in (
        "idx_sessions_agent_id",
        "idx_turns_session_created_at",
        "idx_agent_states_agent_id",
        "idx_entity_mentions_turn_id",
    ):
        assert index_name in names
