from __future__ import annotations

import pytest
from typing import Any, cast

from backend.mcp.working_memory_tools import build_working_memory_health
from backend.working_memory.config import WorkingMemorySettings


pytestmark = pytest.mark.integration


def test_wm_mcp_health_live_contract_without_server() -> None:
    health = build_working_memory_health(WorkingMemorySettings())

    details = cast(dict[str, Any], health["details"])
    assert health["backend"] == "working_memory"
    assert details["collection"] == "quimera_working_memory"
