"""FastMCP server for QUIMERA working memory."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from backend.mcp.working_memory_tools import (
    build_working_memory_health,
    working_memory_cleanup_expired,
    working_memory_query,
    working_memory_restore,
    working_memory_snapshot,
    working_memory_upsert,
)
from backend.working_memory.config import WorkingMemorySettings, get_working_memory_settings


def create_working_memory_server(settings: WorkingMemorySettings | None = None) -> FastMCP[Any]:
    resolved = settings or get_working_memory_settings()
    server: FastMCP[Any] = FastMCP("quimera-working-memory")

    @server.tool
    async def working_memory_health() -> dict[str, object]:
        return build_working_memory_health(resolved)

    @server.tool
    async def working_memory_point_upsert(
        agent_id: str,
        session_id: str,
        memory_kind: str,
        vector: list[float],
        metadata: dict[str, object] | None = None,
        safe_summary: str | None = None,
    ) -> dict[str, object]:
        return await working_memory_upsert(
            agent_id=agent_id,
            session_id=session_id,
            memory_kind=memory_kind,
            vector=vector,
            metadata=metadata,
            safe_summary=safe_summary,
            settings=resolved,
            store=None,
        )

    @server.tool
    async def working_memory_points_query(agent_id: str, session_id: str, query_vector: list[float], limit: int = 10) -> dict[str, object]:
        return await working_memory_query(agent_id, session_id, query_vector, limit=limit, settings=resolved, store=None)

    @server.tool
    async def working_memory_session_snapshot(agent_id: str, session_id: str) -> dict[str, object]:
        return await working_memory_snapshot(agent_id, session_id, snapshot_service=None)

    @server.tool
    async def working_memory_session_restore(agent_id: str, session_id: str) -> dict[str, object]:
        return await working_memory_restore(agent_id, session_id, settings=resolved, restore_service=None)

    @server.tool
    async def working_memory_expired_cleanup(agent_id: str | None = None, session_id: str | None = None) -> dict[str, object]:
        return await working_memory_cleanup_expired(settings=resolved, cleanup_service=None, agent_id=agent_id, session_id=session_id)

    return server


def main() -> int:
    server = create_working_memory_server()
    server.run(transport="streamable-http", host="127.0.0.1", port=8813, path="/mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
