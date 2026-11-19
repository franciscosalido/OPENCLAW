"""DL-PR06: protocolo de latencia — estrutura do relatorio, sem afirmar desempenho."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.derivatives_latency_protocol import (
    SCHEMA_VERSION,
    STEPS,
    TARGET_P95_MS,
    main,
    measure,
    percentile,
)

SYNTHETIC = Path("tests/fixtures/derivatives/synthetic")


def test_percentile_is_nearest_rank() -> None:
    values = [float(index) for index in range(1, 31)]
    assert percentile(values, 50) == 15.0
    assert percentile(values, 95) == 29.0
    assert percentile(values, 99) == 30.0
    assert percentile([7.0], 95) == 7.0
    assert percentile(list(reversed(values)), 95) == 29.0
    with pytest.raises(ValueError, match="vazia"):
        percentile([], 50)


async def test_measure_reports_every_step_for_synthetic_test_data() -> None:
    report = await measure(runs=3, fixture_dir=SYNTHETIC, symbol="BOVA11",
                           expiry=date(2026, 11, 19), root=Path.cwd())
    assert report["schema_version"] == SCHEMA_VERSION
    assert (report["provenance"], report["purpose"]) == ("synthetic", "test")
    assert (report["runs"], report["rows"], report["rows_priced"]) == (3, 100, 100)
    assert report["target_p95_ms"] == TARGET_P95_MS == 2000.0
    stats = report["ms"]
    assert isinstance(stats, dict) and set(stats) == set(STEPS)
    for step in STEPS:
        entry = stats[step]
        assert 0.0 <= entry["p50"] <= entry["p95"] <= entry["p99"] <= entry["max"]
    assert isinstance(report["meets_target"], bool)
    assert set(report["platform"]) == {"system", "machine", "python"}  # type: ignore[call-overload]


async def test_measure_refuses_non_positive_runs() -> None:
    with pytest.raises(ValueError, match="positivo"):
        await measure(runs=0, fixture_dir=SYNTHETIC, symbol="BOVA11",
                      expiry=date(2026, 11, 19), root=Path.cwd())


def test_cli_writes_the_report_outside_tracked_paths(tmp_path: Path) -> None:
    code = main(["--runs", "2", "--out-dir", str(tmp_path)])
    written = list(tmp_path.glob("latency_*.json"))
    assert len(written) == 1
    report = json.loads(written[0].read_text(encoding="utf-8"))
    assert report["runs"] == 2 and "measured_at" in report
    assert code == (0 if report["meets_target"] else 1)
