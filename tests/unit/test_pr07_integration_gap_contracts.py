from __future__ import annotations

from pathlib import Path


def test_pr07_integration_gap_files_exist() -> None:
    for path in (
        "tests/integration/test_pr01_concurrency_gaps.py",
        "tests/integration/test_pr02_market_bars_concurrency.py",
        "tests/integration/test_pr07_pg_indexes_real.py",
    ):
        assert Path(path).exists()

