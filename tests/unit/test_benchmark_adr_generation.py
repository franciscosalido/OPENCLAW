from __future__ import annotations

import json
from pathlib import Path


ADR = Path("docs/ADR/ADR-003-memory-backend-decision.md")
SUMMARY = Path("evaluation/results/rag_01b_session_benchmark_summary.json")


def test_adr_is_accepted_and_references_benchmark_artifacts() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "Status: Accepted" in text
    assert "evaluation/results/rag_01b_session_benchmark_summary.json" in text
    assert "evaluation/results/rag_01b_session_benchmark_rows.csv" in text


def test_adr_reflects_summary_decisions() -> None:
    text = ADR.read_text(encoding="utf-8")
    decisions = json.loads(SUMMARY.read_text(encoding="utf-8"))["decisions"]

    for key, value in decisions.items():
        assert f"{key}: {value}" in text


def test_adr_documents_backend_boundaries() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "Postgres/Timescale" in text
    assert "Qdrant" in text
    assert "Qlib and Kronos use derived projections" in text
    assert "MCP is an agent interface" in text
    assert "llm_response_cache: qdrant" in text
    assert "qdrant_or_litellm_cache" not in text
    assert "PostgreSQL 17" not in text
    assert "Qdrant 1.13" not in text
