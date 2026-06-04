from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "quimera-mcp-response-v1"
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "quimera-mcp-health-v1"
    status: Literal["ok", "fail", "skipped"]
    backend: str
    details: dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    host: str = "127.0.0.1"
    port: int
    path: str = "/mcp"
    transport: str = "streamable-http"

