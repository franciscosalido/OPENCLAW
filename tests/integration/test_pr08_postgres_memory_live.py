from __future__ import annotations

import os

import pytest

from backend.mcp.mcp_config import PostgresMcpConfig
from backend.mcp.postgres_memory_server import create_postgres_memory_server

pytestmark = pytest.mark.integration


async def test_pr08_postgres_mcp_degrades_cleanly_without_dsn() -> None:
    if os.getenv("TEST_POSTGRES_DSN") or os.getenv("QUIMERA_POSTGRES_DSN"):
        pytest.skip(
            "live Postgres DSN present; real roundtrip is covered by PR-01/PR-07 tests"
        )
    server = create_postgres_memory_server(
        PostgresMcpConfig(dsn=None, write_enabled=False)
    )

    result = await server.call_tool(
        "postgres_recent_turns_get",
        {"session_id": "00000000-0000-0000-0000-000000000001", "limit": 2},
    )

    assert result.structured_content is not None
    assert result.structured_content["degraded"] is True
