from __future__ import annotations

import os
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import pytest


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_wm_checkpoint_pgvector_live_schema_applies() -> None:
    dsn = os.environ.get("TEST_POSTGRES_DSN") or os.environ.get("QUIMERA_POSTGRES_DSN")
    if not dsn:
        pytest.skip("set TEST_POSTGRES_DSN to run live pgvector checkpoint test")
    sql = Path("infra/postgres/sql/020_working_memory_checkpoints.sql").read_text(
        encoding="utf-8"
    )
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(sql)
        rows = await conn.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename IN ('working_memory_snapshots', 'working_memory_snapshot_points')
            """
        )
    finally:
        await conn.close()

    assert {row["tablename"] for row in rows} == {
        "working_memory_snapshots",
        "working_memory_snapshot_points",
    }
