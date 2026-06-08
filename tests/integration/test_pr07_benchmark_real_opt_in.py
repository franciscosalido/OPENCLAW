from __future__ import annotations

import os

import pytest

from evaluation.benchmark_safety import BenchmarkBackendUnavailable
from evaluation.compare_session_context_backends import build_summary

pytestmark = pytest.mark.integration


def test_pr07_benchmark_real_mode_is_opt_in() -> None:
    if os.getenv("QUIMERA_BENCHMARK_REAL") != "1":
        pytest.skip("QUIMERA_BENCHMARK_REAL=1 is required")
    assert build_summary(1, real_mode=True)["guards"]["real_mode"] is True  # type: ignore[index]


def test_postgres_container_stopped_during_benchmark() -> None:
    if (
        os.getenv("QUIMERA_TEST_CAN_CONTROL_RUNTIME") != "1"
        or os.getenv("QUIMERA_BENCHMARK_REAL") != "1"
    ):
        pytest.skip("runtime control and real benchmark opt-in are required")
    raise BenchmarkBackendUnavailable(
        "postgres unavailable during controlled benchmark"
    )
