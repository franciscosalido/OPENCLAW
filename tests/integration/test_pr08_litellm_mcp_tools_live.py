from __future__ import annotations

from pathlib import Path

import pytest

from infra.litellm.config_validator import validate_litellm_config

pytestmark = pytest.mark.integration


def test_pr08_litellm_mcp_servers_registered_static_contract() -> None:
    cfg = validate_litellm_config(Path("infra/litellm/litellm_config.yaml"))

    assert "quimera_postgres_memory" in cfg.mcp_servers
    assert "quimera_qdrant_memory" in cfg.mcp_servers
    assert "quimera_working_memory" in cfg.mcp_servers
    assert cfg.agentic0_tool_policy is not None
    assert "postgres_agent_state_upsert" not in cfg.agentic0_tool_policy.allowed_tools
