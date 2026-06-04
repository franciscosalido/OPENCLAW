from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import cast

from evaluation.compare_session_context_backends import build_summary


SUMMARY = Path("evaluation/results/rag_01b_session_benchmark_summary.json")
ROWS = Path("evaluation/results/rag_01b_session_benchmark_rows.csv")


def test_benchmark_summary_schema_and_decisions() -> None:
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))

    assert data["schema_version"] == "rag-01b-session-benchmark-v1"
    assert data["environment"]["postgresql"] == "18.4"
    assert data["environment"]["qdrant"] == "1.18.x"
    assert data["guards"]["QUIMERA_CACHE_ENABLED"] == "0"
    assert data["decisions"]["sessions"] == "postgres"
    assert data["decisions"]["vectors"] == "qdrant"
    assert data["otel_attributes"]["forbidden_attributes_seen"] == []


def test_benchmark_rows_csv_schema() -> None:
    with ROWS.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
            "scenario",
            "backend",
            "sample_index",
            "latency_ms",
            "error",
            "cache_enabled",
            "cache_bypass",
            "git_commit",
            "timestamp",
        ]
        rows = list(reader)

    assert rows
    assert {row["backend"] for row in rows} == {"postgres", "qdrant"}


def test_build_summary_is_deterministic_shape() -> None:
    summary = build_summary(10)
    scenarios = cast(list[dict[str, object]], summary["scenarios"])
    decisions = cast(dict[str, str], summary["decisions"])

    assert len(scenarios) == 4
    assert decisions["semantic_cache"] == "qdrant"
