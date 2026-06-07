from __future__ import annotations

from pathlib import Path

from infra.litellm.config_validator import validate_litellm_config


def test_agentic0_allowed_tools_are_explicit_and_non_destructive() -> None:
    cfg = validate_litellm_config(Path("infra/litellm/litellm_config.yaml"))

    assert cfg.agentic0_tool_policy is not None
    tools = set(cfg.agentic0_tool_policy.allowed_tools)
    assert "*" not in tools
    assert not any("delete" in tool or "recreate" in tool or "store" in tool for tool in tools)
    assert "postgres_agent_state_upsert" not in tools
    assert "postgres_agent_state_upsert" in cfg.agentic0_tool_policy.optional_write_tools
    assert "working_memory_health" in tools
    assert "working_memory_points_query" in tools
    assert "working_memory_point_upsert" not in tools
    assert "working_memory_point_upsert" in cfg.agentic0_tool_policy.optional_write_tools
    assert "working_memory_session_restore" not in tools
    assert "working_memory_expired_cleanup" not in tools
    assert cfg.agentic0_tool_policy.virtual_key_name == "agentic0-smoke"
    assert cfg.agentic0_tool_policy.destructive_tools_allowed is False


def test_mcp_servers_remain_loopback_and_not_public() -> None:
    cfg = validate_litellm_config(Path("infra/litellm/litellm_config.yaml"))

    assert set(cfg.mcp_servers) == {
        "quimera-postgres-memory",
        "quimera-qdrant-memory",
        "quimera-working-memory",
    }
    for server in cfg.mcp_servers.values():
        assert server.url.startswith("http://127.0.0.1:")
        assert server.available_on_public_internet is False
