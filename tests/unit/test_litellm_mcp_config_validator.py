from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from infra.litellm.config_validator import ConfigRoot, load_raw_config, validate_config


CONFIG = Path("infra/litellm/litellm_config.yaml")


def test_litellm_accepts_loopback_mcp_servers() -> None:
    cfg = validate_config(CONFIG, strict=False)

    assert "quimera_postgres_memory" in cfg.mcp_servers
    assert cfg.mcp_servers["quimera_postgres_memory"].url == "http://127.0.0.1:8811/mcp"
    assert cfg.mcp_servers["quimera_qdrant_memory"].available_on_public_internet is False
    assert cfg.mcp_servers["quimera_working_memory"].url == "http://127.0.0.1:8813/mcp"


def test_litellm_rejects_public_mcp_server_url() -> None:
    raw = deepcopy(load_raw_config(CONFIG))
    raw["mcp_servers"]["bad_public"] = {
        "url": "http://0.0.0.0:8813/mcp",
        "transport": "http",
        "available_on_public_internet": False,
    }

    with pytest.raises(ValueError):
        ConfigRoot.model_validate(raw)


def test_litellm_rejects_sse_and_public_internet() -> None:
    raw = deepcopy(load_raw_config(CONFIG))
    raw["mcp_servers"]["bad_sse"] = {
        "url": "http://127.0.0.1:8813/mcp",
        "transport": "sse",
        "available_on_public_internet": True,
    }

    with pytest.raises(ValueError):
        ConfigRoot.model_validate(raw)


def test_litellm_rejects_hyphenated_mcp_server_names() -> None:
    raw = deepcopy(load_raw_config(CONFIG))
    raw["mcp_servers"]["bad-name"] = {
        "url": "http://127.0.0.1:8813/mcp",
        "transport": "http",
        "available_on_public_internet": False,
    }

    with pytest.raises(ValueError, match="snake_case"):
        ConfigRoot.model_validate(raw)
