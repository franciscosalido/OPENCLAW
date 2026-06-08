from __future__ import annotations

from infra.litellm.overhead_benchmark import (
    calculate_overhead_stats,
    run_live_benchmark,
    skipped_report,
)


def test_benchmark_is_opt_in() -> None:
    report = run_live_benchmark(env={})

    assert report["status"] == "SKIPPED_VALID"
    assert report["skipped"] is True
    assert report["overhead_ms"] is None


def test_skipped_report_is_valid() -> None:
    report = skipped_report()

    assert report["schema_version"] == "quimera-litellm-overhead-v1"
    assert report["status"] == "SKIPPED_VALID"
    assert report["skipped"] is True


def test_calculates_percentiles_and_mean() -> None:
    stats = calculate_overhead_stats([10, 20, 30, 40, 50])

    assert stats.samples == 5
    assert stats.p50_ms == 30
    assert stats.p95_ms == 48
    assert stats.p99_ms == 49.6
    assert stats.mean_ms == 30
