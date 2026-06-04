from __future__ import annotations

from backend.mcp.qdrant_memory_server import create_qdrant_memory_server


async def test_qdrant_mcp_tools_are_registered() -> None:
    server = create_qdrant_memory_server()
    tools = {tool.name for tool in await server.list_tools()}

    assert "qdrant_memory_health" in tools
    assert "qdrant_collection_list" in tools
    assert "qdrant_scroll_safe" in tools


async def test_qdrant_mcp_scroll_does_not_expose_vectors() -> None:
    server = create_qdrant_memory_server()
    result = await server.call_tool("qdrant_scroll_safe", {"collection_name": "quimera_query_cache", "limit": 3})

    assert result.structured_content is not None
    assert result.structured_content["data"]["vectors_exposed"] is False
