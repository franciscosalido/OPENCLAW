"""Safe report generation for the PR-08 Agentic0 smoke."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from integration.agentic0_contracts import Agentic0SmokeResult
from integration.safety_scan import assert_no_forbidden_fields

SMOKE_SUMMARY_PATH = Path("evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json")
HEALTH_PATH = Path("evaluation/results/rag_01b_pr08_integration_health.json")
LATENCY_PATH = Path("evaluation/results/rag_01b_pr08_latency_summary.json")
MARKDOWN_PATH = Path("docs/rag/rag_01b_pr08_integration_report.md")


def write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    assert_no_forbidden_fields(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_smoke_artifacts(result: Agentic0SmokeResult) -> None:
    payload = smoke_summary_payload(result)
    write_json_artifact(SMOKE_SUMMARY_PATH, payload)
    latency = cast("dict[str, Any]", payload["latency"])
    write_json_artifact(LATENCY_PATH, {"schema_version": "rag-01b-pr08-latency-v1", **latency})
    write_markdown_report(MARKDOWN_PATH, payload)


def smoke_summary_payload(result: Agentic0SmokeResult) -> dict[str, Any]:
    payload = result.to_jsonable()
    tool_calls = cast("list[dict[str, Any]]", payload["tool_calls"])
    return {
        "schema_version": "rag-01b-pr08-agentic0-smoke-v1",
        "run_id": payload["run_id"],
        "status": payload["status"],
        "generated_at": payload["finished_at"],
        "correlation_id": payload["correlation_id"],
        "gateway": {"litellm_base_url": "http://127.0.0.1:4000", "host_only": True},
        "services": payload["services"],
        "hybridrag": payload["retrieval"],
        "postgres_memory": payload["postgres_memory"],
        "mcp": {
            "postgres_tool_ok": any(call["server_name"] == "quimera_postgres_memory" and call["status"] in {"ok", "degraded"} for call in tool_calls),
            "qdrant_tool_ok": any(call["server_name"] == "quimera_qdrant_memory" and call["status"] == "ok" for call in tool_calls),
            "allowed_tools_enforced": True,
            "virtual_key_checked": False,
        },
        "llm": payload["llm"],
        "latency": payload["latency"],
        "safety": payload["safety"],
        "trace_ids": payload["trace_ids"],
        "warnings": payload["warnings"],
    }


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    assert_no_forbidden_fields(payload)
    lines = [
        "# RAG-01B PR-08 Integration Report",
        "",
        f"Status: `{payload['status']}`",
        f"Correlation ID: `{payload['correlation_id']}`",
        "",
        "## Services",
        "",
    ]
    services = payload.get("services", {})
    if isinstance(services, dict):
        for name, status in sorted(services.items()):
            lines.append(f"- `{name}`: `{status}`")
    lines.extend(
        [
            "",
            "## HybridRAG",
            "",
            f"- quality_mode: `{payload['hybridrag']['quality_mode']}`",
            f"- quality_evidence: `{payload['hybridrag']['quality_evidence']}`",
            f"- live_quality_checked: `{payload['hybridrag']['live_quality_checked']}`",
            f"- quality_warning: `{payload['hybridrag']['quality_warning']}`",
            f"- dense_ok: `{payload['hybridrag']['dense_ok']}`",
            f"- sparse_ok: `{payload['hybridrag']['sparse_ok']}`",
            f"- hybrid_ok: `{payload['hybridrag']['hybrid_ok']}`",
            "",
            "## Latency",
            "",
            f"- measurement_mode: `{payload['latency']['measurement_mode']}`",
            f"- sample_count: `{payload['latency']['sample_count']}`",
            f"- p95_ms: `{payload['latency']['p95_ms']}`",
            f"- p95_warning: `{payload['latency']['p95_warning']}`",
            "",
            "## Agentic0",
            "",
            f"- final status: `{payload['status']}`",
            f"- model: `{payload['llm']['model']}`",
            "",
            "## Warnings",
            "",
        ]
    )
    warnings = payload.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## PR-09 Handoff", "", "- Multi-agent permissions, Kronos and autonomous tool-use hardening."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
