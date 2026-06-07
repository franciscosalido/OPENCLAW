from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_pr08_agentic0_runtime_has_no_backend_shortcuts() -> None:
    text = Path("integration/agentic0_client.py").read_text(encoding="utf-8")

    assert "asyncpg" not in text
    assert "qdrant_client" not in text
    assert "127.0.0.1:11434" not in text
    assert "127.0.0.1:6333" not in text
