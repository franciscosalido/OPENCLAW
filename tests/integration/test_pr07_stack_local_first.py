from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr07_stack_is_local_first_static_contract() -> None:
    compose = Path("infra/docker/compose.quimera.local.yml").read_text(encoding="utf-8")
    litellm = Path("infra/litellm/litellm_config.yaml").read_text(encoding="utf-8")

    assert "127.0.0.1:5432:5432" in compose
    assert "127.0.0.1:6333:6333" in compose
    assert "POSTGRES_PASSWORD_FILE" in compose
    assert "POSTGRES_PASSWORD=" not in compose
    assert "quimera-litellm" not in compose
    assert "http://127.0.0.1:8811/mcp" in litellm
    assert "http://127.0.0.1:8812/mcp" in litellm
    assert "0.0.0.0:8811" not in litellm
    assert "0.0.0.0:8812" not in litellm

