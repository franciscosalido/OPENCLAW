from __future__ import annotations

import os

import pytest

from infra.litellm.overhead_benchmark import OVERHEAD_P95_BUDGET_MS, run_live_benchmark


pytestmark = pytest.mark.integration


def test_litellm_overhead_benchmark_opt_in() -> None:
    if os.environ.get("QUIMERA_LITELLM_BENCHMARK") != "1":
        pytest.skip("QUIMERA_LITELLM_BENCHMARK=1 is required")

    report = run_live_benchmark(
        samples=int(os.environ.get("QUIMERA_LITELLM_BENCHMARK_SAMPLES", "5"))
    )
    if report["status"] == "diagnostic_warning":
        pytest.skip("LiteLLM/Ollama benchmark environment is not stable")

    assert report["overhead_ms"]["samples"] >= 1
    assert report["overhead_ms"]["p95_ms"] < OVERHEAD_P95_BUDGET_MS
