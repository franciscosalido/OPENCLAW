from __future__ import annotations

from pathlib import Path

import pytest

from integration import report_writer, run_agentic0_smoke_test
from integration.run_agentic0_smoke_test import run_smoke

pytestmark = pytest.mark.integration


async def test_agentic0_deterministic_smoke_generates_safe_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "SMOKE_SUMMARY_PATH",
        "HEALTH_PATH",
        "LATENCY_PATH",
        "MARKDOWN_PATH",
    ):
        monkeypatch.setattr(
            report_writer, name, tmp_path / getattr(report_writer, name).name
        )
    monkeypatch.setattr(
        run_agentic0_smoke_test, "HEALTH_PATH", report_writer.HEALTH_PATH
    )
    result = await run_smoke(allow_degraded=True)

    assert result.schema_version == "quimera-agentic0-smoke-v1"
    assert result.status in {"pass", "skipped", "fail"}
    assert result.correlation_id
    assert result.retrieval.hybrid_ok is True
    assert result.safety.secrets_seen is False
    assert result.safety.vectors_seen is False
