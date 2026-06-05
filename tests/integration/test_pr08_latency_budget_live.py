from __future__ import annotations

import pytest

from integration.run_agentic0_smoke_test import run_smoke

pytestmark = pytest.mark.integration


async def test_pr08_latency_budget_is_measured_without_hard_gate() -> None:
    result = await run_smoke(allow_degraded=True)

    assert result.latency.total_ms >= 0
    assert result.latency.mcp_ms >= 0
    assert result.latency.llm_ms >= 0
    assert result.warnings is not None
