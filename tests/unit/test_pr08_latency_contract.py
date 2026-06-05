from __future__ import annotations

from integration.run_agentic0_smoke_test import build_latency_summary


def test_latency_summary_marks_p95_unmeasured_when_stack_is_down() -> None:
    summary = build_latency_summary(
        total_ms=42.0,
        health={
            "services": {"litellm": "fail", "ollama": "ok", "qdrant": "fail", "postgres": "fail"},
            "service_latencies_ms": {"ollama": 2.0, "qdrant": 3.0},
        },
    )

    assert summary.measurement_mode == "degraded_no_live_stack"
    assert summary.sample_count == 0
    assert summary.p50_ms is None
    assert summary.p95_ms is None
    assert summary.p95_warning == "not_measured_stack_unavailable"


def test_latency_summary_warns_when_live_p95_exceeds_budget() -> None:
    summary = build_latency_summary(
        total_ms=900.0,
        health={
            "services": {"litellm": "ok", "ollama": "ok", "qdrant": "ok", "postgres": "ok"},
            "service_latencies_ms": {"litellm": 10.0, "ollama": 20.0, "qdrant": 30.0, "postgres": 40.0},
        },
    )

    assert summary.measurement_mode == "live_healthcheck_probe"
    assert summary.sample_count == 5
    assert summary.p95_ms is not None
    assert summary.p95_ms > 500.0
    assert summary.p95_warning == "p95_exceeds_500ms"
