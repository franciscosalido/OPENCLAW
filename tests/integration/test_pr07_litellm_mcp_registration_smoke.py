from __future__ import annotations

import pytest

from infra.litellm.config_validator import validate_config

pytestmark = pytest.mark.integration


def test_litellm_mcp_registration_validates_offline() -> None:
    cfg = validate_config(
        __import__("pathlib").Path("infra/litellm/litellm_config.yaml"), strict=False
    )

    assert set(cfg.mcp_servers) == {
        "quimera_postgres_memory",
        "quimera_qdrant_memory",
        "quimera_working_memory",
    }
