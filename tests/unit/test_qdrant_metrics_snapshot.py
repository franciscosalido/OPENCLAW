"""Offline tests for the Qdrant metrics snapshot helper."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import collect_qdrant_metrics_snapshot as snapshot

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "collect_qdrant_metrics_snapshot.py"

METRICS_TEXT = """
# HELP app_info App information
app_info{name="qdrant",version="1.18.1"} 1
qdrant_app_info{name="qdrant",version="1.18.1"} 1
process_resident_memory_bytes 123456
qdrant_memory_resident_bytes 234567
collection_points{collection="quimera_benchmark_hybrid_118_qwen3"} 56
qdrant_collection_points{id="quimera_benchmark_hybrid_118_qwen3"} 56
collection_vectors{collection="quimera_benchmark_hybrid_118_qwen3",vector="dense"} 56
collection_vectors{collection="quimera_benchmark_hybrid_118_qwen3",vector="sparse"} 56
"""


def test_parse_metrics_snapshot_extracts_safe_fields() -> None:
    parsed = snapshot.parse_metrics_snapshot(
        collection="quimera_benchmark_hybrid_118_qwen3",
        metrics_text=METRICS_TEXT,
        snapshot_at_utc="2026-05-28T00:00:00Z",
    )

    assert parsed.to_safe_dict() == {
        "schema_version": "qdrant-metrics-snapshot-v1",
        "snapshot_at_utc": "2026-05-28T00:00:00Z",
        "collection": "quimera_benchmark_hybrid_118_qwen3",
        "qdrant_server_version": "1.18.1",
        "memory_resident_bytes": 234567,
        "collection_vectors": 112,
        "collection_points": 112,
        "metrics_endpoint": "/metrics?per_collection=true",
        "telemetry_endpoint": "/telemetry",
        "notes": [
            "read_only_metrics_snapshot",
            "no_sensitive_text_or_raw_vectors",
        ],
    }


def test_parse_metrics_snapshot_uses_telemetry_version_fallback() -> None:
    parsed = snapshot.parse_metrics_snapshot(
        collection="quimera_benchmark_hybrid_118_qwen3",
        metrics_text='collection_points{collection="quimera_benchmark_hybrid_118_qwen3"} 1',
        telemetry={"result": {"app": {"version": "1.18.1"}}},
    )

    assert parsed.qdrant_server_version == "1.18.1"


def test_snapshot_json_excludes_sensitive_terms() -> None:
    parsed = snapshot.parse_metrics_snapshot(
        collection="quimera_benchmark_hybrid_118_qwen3",
        metrics_text=METRICS_TEXT,
    )
    encoded = json.dumps(parsed.to_safe_dict(), sort_keys=True).lower()

    for forbidden in (
        "query_text",
        "chunk_text",
        "document_text",
        "payload",
        "embedding",
        "prompt",
        "answer",
    ):
        assert forbidden not in encoded


def test_collection_name_rejects_null_byte() -> None:
    with pytest.raises(ValueError, match="null byte"):
        snapshot.parse_metrics_snapshot(collection="bad\x00name", metrics_text="")


def test_write_snapshot_json_parseable(tmp_path: Path) -> None:
    parsed = snapshot.parse_metrics_snapshot(
        collection="quimera_benchmark_hybrid_118_qwen3",
        metrics_text=METRICS_TEXT,
    )
    output = tmp_path / "snapshot.json"

    snapshot.write_snapshot(parsed, output)

    assert json.loads(output.read_text(encoding="utf-8"))["collection_points"] == 112


def test_script_has_no_collection_mutation_calls() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "create_collection",
        "delete_collection",
        "recreate_collection",
        "update_collection",
        "upsert",
        "delete",
        "set_payload",
        "delete_payload",
        "upload_collection",
        "delete_vectors",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden
