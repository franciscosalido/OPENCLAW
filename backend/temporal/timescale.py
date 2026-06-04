"""Small TimescaleDB helpers for Janus temporal finance memory."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import asyncpg  # type: ignore[import-untyped]


async def is_timescale_available(conn: Any) -> bool:
    """Return whether the TimescaleDB extension is available to this database."""

    value = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = $1)",
        "timescaledb",
    )
    return bool(value)


async def is_hypertable(conn: Any, table_name: str) -> bool:
    """Return whether a table is registered as a TimescaleDB hypertable."""

    if not table_name.strip():
        raise ValueError("table_name cannot be empty")
    value = await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public'
              AND hypertable_name = $1
        )
        """,
        table_name,
    )
    return bool(value)


async def require_hypertables(
    conn: asyncpg.Connection,
    table_names: Sequence[str],
) -> None:
    """Raise if any required TimescaleDB hypertable is missing."""

    missing: list[str] = []
    for table_name in table_names:
        if not await is_hypertable(conn, table_name):
            missing.append(table_name)
    if missing:
        raise RuntimeError(f"missing TimescaleDB hypertables: {', '.join(missing)}")
