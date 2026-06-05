from __future__ import annotations

import pytest

from integration.run_agentic0_smoke_test import run_smoke

pytestmark = pytest.mark.integration


async def test_agentic0_deterministic_smoke_generates_safe_summary() -> None:
    result = await run_smoke(allow_degraded=True)

    assert result.schema_version == "quimera-agentic0-smoke-v1"
    assert result.status in {"pass", "skipped", "fail"}
    assert result.correlation_id
    assert result.retrieval.hybrid_ok is True
    assert result.safety.secrets_seen is False
    assert result.safety.vectors_seen is False
