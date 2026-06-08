from __future__ import annotations

import json
from pathlib import Path

import pytest

from integration.smoke_summary import build_smoke_summary, compare_latency_baseline


BASELINE = Path("baseline/rag01b_latency_baseline.json")


def test_latency_baseline_exists_and_thresholds_are_positive() -> None:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert data["schema_version"] == "quimera-latency-baseline-v1"
    assert data["regression_multiplier"] >= 1.0
    for key in (
        "postgres_p95_ms",
        "qdrant_p95_ms",
        "litellm_p95_ms",
        "agentic0_p95_ms",
    ):
        assert data[key] > 0


def test_latency_regression_detection_modes() -> None:
    baseline = {"postgres_p95_ms": 50.0, "regression_multiplier": 2.0}
    current = {"postgres_p95_ms": 120.0}

    quick = compare_latency_baseline(current, baseline, mode="quick")
    full = compare_latency_baseline(current, baseline, mode="full")

    assert quick["regressions"]
    assert quick["exit_code"] == 0
    assert full["exit_code"] == 5


def test_smoke_summary_exposes_status_alias_for_overall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "integration.smoke_summary.build_integration_health_report",
        lambda: {
            "overall": "ok",
            "services": {
                "postgres": "ok",
                "qdrant": "ok",
                "litellm": "ok",
                "ollama": "ok",
            },
            "mcp_servers": {},
            "service_latencies_ms": {},
            "warnings": [],
        },
    )
    summary = build_smoke_summary(mode="quick")

    assert summary["overall"] == "ok"
    assert summary["status"] == summary["overall"]
