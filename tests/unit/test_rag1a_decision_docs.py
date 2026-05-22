"""Structural tests for the RAG-1A decision report and ADR."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "docs" / "rag" / "rag1a_results.md"
ADR_PATH = ROOT / "docs" / "ADR" / "ADR-0XX-hybrid-retrieval-foundation.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_block(markdown: str, marker: str) -> dict[str, Any]:
    pattern = rf"<!-- machine-readable: {re.escape(marker)} -->\s*```json\s*(.*?)\s*```"
    match = re.search(pattern, markdown, flags=re.DOTALL)
    assert match is not None, f"missing machine-readable block {marker}"
    parsed = json.loads(match.group(1))
    assert isinstance(parsed, dict)
    return cast(dict[str, Any], parsed)


def test_report_and_adr_exist() -> None:
    assert REPORT_PATH.exists()
    assert ADR_PATH.exists()


def test_machine_readable_json_parses() -> None:
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    adr = _json_block(_read(ADR_PATH), "rag1a-adr-decision-v1")

    assert report["schema_version"] == "rag1a-decision-v1"
    assert adr["schema_version"] == "rag1a-adr-decision-v1"


def test_privacy_flags_are_safe() -> None:
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    privacy = cast(dict[str, object], report["privacy"])

    assert privacy == {
        "includes_query_text": False,
        "includes_document_text": False,
        "includes_payload": False,
        "includes_vectors": False,
        "query_is_redacted": True,
    }


def test_adr_contains_rollback_reversal_options_and_followups() -> None:
    adr = _read(ADR_PATH)

    assert "## Rollback" in adr
    assert "## Reversal Conditions" in adr
    assert "## Considered Options" in adr
    assert "## Observability Contract" in adr
    assert "## Follow-ups" in adr


def test_report_contains_limitations_and_no_synthetic_hedge() -> None:
    report = _read(REPORT_PATH)

    assert "## Limitations" in report
    assert "The current sprint benchmark is synthetic by design." in report
    assert "expected to be synthetic" not in report
    assert "financial safety" in report


def test_decision_accepted_not_allowed_with_null_metrics() -> None:
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    dense = cast(dict[str, object], report["dense_baseline"])
    hybrid = cast(dict[str, object], report["hybrid_result"])

    has_null_metric = any(value is None for value in dense.values()) or any(
        value is None for value in hybrid.values()
    )
    assert has_null_metric
    assert report["decision"] == "inconclusive_collect_more_evidence"

    adr = _read(ADR_PATH)
    assert "## Status\n\nDeferred." in adr
    assert "## Status\n\nAccepted" not in adr


def test_machine_readable_blocks_do_not_use_forbidden_data_keys() -> None:
    forbidden_keys = {
        "query",
        "query_text",
        "text",
        "chunk_text",
        "document_text",
        "payload",
        "prompt",
        "answer",
        "vector",
        "embedding",
    }
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    adr = _json_block(_read(ADR_PATH), "rag1a-adr-decision-v1")

    assert not _contains_forbidden_key(report, forbidden_keys)
    assert not _contains_forbidden_key(adr, forbidden_keys)


def test_collection_names_correct_and_unambiguous() -> None:
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    promotion = cast(dict[str, object], report["promotion"])

    assert promotion["candidate_collection"] == "quimera_knowledge_v2"
    assert promotion["promoted_collection"] is None
    assert promotion["protected_collection"] == "quimera_knowledge"
    assert promotion["mode"] == "none"

    adr = _json_block(_read(ADR_PATH), "rag1a-adr-decision-v1")
    assert adr["candidate_collection"] == "quimera_knowledge_v2"
    assert adr["promoted_collection"] is None
    assert adr["protected_collection"] == "quimera_knowledge"


def test_json_deltas_are_future_ready() -> None:
    report = _json_block(_read(REPORT_PATH), "rag1a-decision-v1")
    deltas = cast(dict[str, object], report["deltas"])

    assert {
        "recall_at_10_abs",
        "recall_at_10_pct",
        "ndcg_at_5_abs",
        "ndcg_at_5_pct",
        "latency_p95_multiplier",
        "dense_win_rate",
    }.issubset(deltas.keys())


def test_nominal_pr_provenance_is_documented() -> None:
    adr = _read(ADR_PATH)

    assert "RRF fusion: PR-07" in adr
    assert "Hybrid retriever: PR-08" in adr
    assert "Hybrid ingest: PR-09" in adr


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden:
                return True
            if _contains_forbidden_key(nested, forbidden):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False
