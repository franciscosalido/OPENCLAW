from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import asyncpg  # type: ignore[import-untyped]
from fastmcp import FastMCP

from backend.mcp.mcp_config import PostgresMcpConfig, load_postgres_mcp_config
from backend.mcp.mcp_models import HealthResponse, ToolResponse
from backend.mcp.mcp_safety import (
    validate_limit,
    validate_non_empty_text,
    validate_safe_mapping,
    validate_uuid,
)


@asynccontextmanager
async def postgres_lifespan(_server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
    config = load_postgres_mcp_config()
    pool: asyncpg.Pool | None = None
    if config.dsn:
        pool = await asyncpg.create_pool(dsn=config.dsn, min_size=1, max_size=3)
    try:
        yield {"pool": pool, "config": config}
    finally:
        if pool is not None:
            await pool.close()


def create_postgres_memory_server(
    config: PostgresMcpConfig | None = None,
) -> FastMCP[Any]:
    resolved = config or load_postgres_mcp_config()
    server: FastMCP[Any] = FastMCP(
        "quimera-postgres-memory", lifespan=postgres_lifespan
    )
    degraded = not bool(resolved.dsn)

    @server.tool
    async def postgres_memory_health() -> dict[str, object]:
        return HealthResponse(
            status="skipped" if degraded else "ok",
            backend="postgres",
            details={"dsn_present": bool(resolved.dsn), "degraded": degraded},
        ).model_dump()

    @server.tool
    async def postgres_session_get(session_id: str) -> dict[str, object]:
        validate_uuid(session_id, "session_id")
        return ToolResponse(
            ok=True,
            degraded=degraded,
            data={"session_id": session_id, "source": "postgres"},
        ).model_dump()

    @server.tool
    async def postgres_recent_turns_get(
        session_id: str, limit: int = 20
    ) -> dict[str, object]:
        validate_uuid(session_id, "session_id")
        validate_limit(limit)
        return ToolResponse(
            ok=True,
            degraded=degraded,
            data={"session_id": session_id, "turns": [], "limit": limit},
        ).model_dump()

    @server.tool
    async def postgres_agent_state_get(
        agent_id: str, session_id: str, state_key: str
    ) -> dict[str, object]:
        validate_non_empty_text(agent_id, "agent_id")
        validate_uuid(session_id, "session_id")
        validate_non_empty_text(state_key, "state_key")
        return ToolResponse(
            ok=True,
            degraded=degraded,
            data={
                "agent_id": agent_id,
                "session_id": session_id,
                "state_key": state_key,
            },
        ).model_dump()

    @server.tool
    async def postgres_entity_mentions_for_turn(turn_id: str) -> dict[str, object]:
        validate_uuid(turn_id, "turn_id")
        return ToolResponse(
            ok=True, degraded=degraded, data={"turn_id": turn_id, "mentions": []}
        ).model_dump()

    @server.tool
    async def postgres_agent_state_upsert(
        agent_id: str,
        session_id: str,
        state_key: str,
        state_value: Mapping[str, object],
    ) -> dict[str, object]:
        if not resolved.write_enabled:
            return ToolResponse(
                ok=False, degraded=degraded, error="postgres MCP write disabled"
            ).model_dump()
        validate_non_empty_text(agent_id, "agent_id")
        validate_uuid(session_id, "session_id")
        validate_non_empty_text(state_key, "state_key")
        validate_safe_mapping(state_value)
        if degraded:
            return ToolResponse(
                ok=False, degraded=True, error="postgres backend unavailable"
            ).model_dump()
        return ToolResponse(
            ok=True,
            data={
                "agent_id": agent_id,
                "session_id": session_id,
                "state_key": state_key,
            },
        ).model_dump()

    return server


def main() -> int:
    server = create_postgres_memory_server()
    server.run(transport="streamable-http", host="127.0.0.1", port=8811, path="/mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
