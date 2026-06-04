from __future__ import annotations

from backend.mcp.mcp_config import PostgresMcpConfig
from backend.mcp.postgres_memory_server import create_postgres_memory_server


async def test_postgres_mcp_tools_are_registered() -> None:
    server = create_postgres_memory_server(PostgresMcpConfig(write_enabled=False))
    tools = {tool.name for tool in await server.list_tools()}

    assert "postgres_memory_health" in tools
    assert "postgres_recent_turns_get" in tools
    assert "postgres_agent_state_upsert" in tools


async def test_postgres_mcp_write_disabled_by_default() -> None:
    server = create_postgres_memory_server(PostgresMcpConfig(write_enabled=False))
    result = await server.call_tool(
        "postgres_agent_state_upsert",
        {
            "agent_id": "agent",
            "session_id": "00000000-0000-0000-0000-000000000001",
            "state_key": "plan",
            "state_value": {"v": 1},
        },
    )

    assert result.structured_content is not None
    assert result.structured_content["ok"] is False
    assert result.structured_content["degraded"] is True


async def test_postgres_mcp_read_tools_mark_degraded_without_dsn() -> None:
    server = create_postgres_memory_server(PostgresMcpConfig(dsn=None, write_enabled=False))

    result = await server.call_tool(
        "postgres_recent_turns_get",
        {"session_id": "00000000-0000-0000-0000-000000000001", "limit": 3},
    )

    assert result.structured_content is not None
    assert result.structured_content["ok"] is True
    assert result.structured_content["degraded"] is True
