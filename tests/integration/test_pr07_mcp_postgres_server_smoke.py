from __future__ import annotations

import pytest

from backend.mcp.postgres_memory_server import create_postgres_memory_server

pytestmark = pytest.mark.integration


async def test_pr07_mcp_postgres_tools_listable() -> None:
    server = create_postgres_memory_server()
    tools = {tool.name for tool in await server.list_tools()}

    assert "postgres_memory_health" in tools
