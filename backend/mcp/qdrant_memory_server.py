from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from backend.mcp.mcp_config import QdrantMcpConfig, load_qdrant_mcp_config
from backend.mcp.mcp_models import HealthResponse, ToolResponse
from backend.mcp.mcp_safety import validate_collection_name, validate_limit


def create_qdrant_memory_server(config: QdrantMcpConfig | None = None) -> FastMCP[Any]:
    resolved = config or load_qdrant_mcp_config()
    server: FastMCP[Any] = FastMCP("quimera-qdrant-memory")

    @server.tool
    async def qdrant_memory_health() -> dict[str, object]:
        return HealthResponse(status="skipped", backend="qdrant", details={"url": resolved.url}).model_dump()

    @server.tool
    async def qdrant_query_cache_health() -> dict[str, object]:
        return ToolResponse(ok=True, data={"collection": "quimera_query_cache", "vectors_exposed": False}).model_dump()

    @server.tool
    async def qdrant_collection_list() -> dict[str, object]:
        return ToolResponse(ok=True, data={"collections": [], "vectors_exposed": False}).model_dump()

    @server.tool
    async def qdrant_collection_info(collection_name: str) -> dict[str, object]:
        clean = validate_collection_name(collection_name)
        return ToolResponse(ok=True, data={"collection_name": clean, "vectors_exposed": False}).model_dump()

    @server.tool
    async def qdrant_scroll_safe(collection_name: str, limit: int = 10) -> dict[str, object]:
        clean = validate_collection_name(collection_name)
        validate_limit(limit)
        return ToolResponse(ok=True, data={"collection_name": clean, "points": [], "vectors_exposed": False}).model_dump()

    return server


def main() -> int:
    server = create_qdrant_memory_server()
    server.run(transport="streamable-http", host="127.0.0.1", port=8812, path="/mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

