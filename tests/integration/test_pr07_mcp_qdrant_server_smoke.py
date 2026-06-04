from __future__ import annotations

import pytest

from backend.mcp.qdrant_memory_server import create_qdrant_memory_server

pytestmark = pytest.mark.integration


async def test_pr07_mcp_qdrant_tools_listable() -> None:
    server = create_qdrant_memory_server()
    tools = {tool.name for tool in await server.list_tools()}

    assert "qdrant_memory_health" in tools
