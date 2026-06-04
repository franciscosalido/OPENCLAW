from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostgresMcpConfig:
    host: str = "127.0.0.1"
    port: int = 8811
    path: str = "/mcp"
    write_enabled: bool = False
    dsn: str | None = None


@dataclass(frozen=True, slots=True)
class QdrantMcpConfig:
    host: str = "127.0.0.1"
    port: int = 8812
    path: str = "/mcp"
    url: str = "http://127.0.0.1:6333"


def load_postgres_mcp_config(env: dict[str, str] | None = None) -> PostgresMcpConfig:
    env_map = os.environ if env is None else env
    return PostgresMcpConfig(
        write_enabled=env_map.get("QUIMERA_MCP_POSTGRES_WRITE_ENABLED") == "1",
        dsn=env_map.get("QUIMERA_POSTGRES_DSN") or env_map.get("TEST_POSTGRES_DSN"),
    )


def load_qdrant_mcp_config(env: dict[str, str] | None = None) -> QdrantMcpConfig:
    env_map = os.environ if env is None else env
    return QdrantMcpConfig(url=env_map.get("QDRANT_API_BASE", "http://127.0.0.1:6333"))
