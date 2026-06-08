from __future__ import annotations

import pytest

from integration.run_agentic0_smoke_test import run_smoke

pytestmark = pytest.mark.integration


async def test_pr08_latency_budget_is_measured_without_hard_gate() -> None:
    result = await run_smoke(allow_degraded=True)

    assert result.latency.total_ms >= 0
    assert result.latency.mcp_ms >= 0
    assert result.latency.llm_ms >= 0
    assert result.latency.measurement_mode in {
        "live_healthcheck_probe",
        "degraded_no_live_stack",
    }
    if result.latency.measurement_mode == "live_healthcheck_probe":
        assert result.latency.sample_count > 0
        assert result.latency.p95_ms is not None
        if result.latency.p95_ms > 500.0:
            assert result.latency.p95_warning == "p95_exceeds_500ms"
    else:
        assert result.latency.sample_count == 0
        assert result.latency.p95_warning == "not_measured_stack_unavailable"
    assert result.warnings is not None
