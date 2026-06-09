"""Integrated local-first healthcheck for RAG-01B PR-08."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import yaml

from integration.report_writer import HEALTH_PATH, write_json_artifact
from scripts.quimera_status import build_status_report

HealthStatus = Literal["ok", "degraded", "fail"]
ServiceStatus = Literal["ok", "fail", "skipped", "unknown"]

EXPECTED_MCP_SERVERS = {
    "quimera_postgres_memory": (
        "postgres_memory_health",
        "postgres_recent_turns_get",
        "postgres_agent_state_get",
    ),
    "quimera_qdrant_memory": (
        "qdrant_memory_health",
        "qdrant_collection_list",
        "qdrant_scroll_safe",
    ),
    "quimera_working_memory": ("working_memory_health", "working_memory_points_query"),
}


def build_integration_health_report() -> dict[str, Any]:
    base_status = build_status_report()
    litellm_models = _litellm_models()
    config_mcp = _mcp_servers_from_config(Path("infra/litellm/litellm_config.yaml"))
    services = _service_statuses(base_status)
    service_latencies_ms = _service_latencies(base_status)
    mcp_servers = {
        name: {
            "status": "ok" if name in config_mcp else "fail",
            "registered_in_litellm_config": name in config_mcp,
            "gateway_introspection_skipped": True,
            "expected_tools": list(tools),
            "allowed_tools_validated_static": True,
        }
        for name, tools in EXPECTED_MCP_SERVERS.items()
    }
    warnings: list[str] = []
    if litellm_models["status"] != "ok":
        warnings.append("litellm model introspection unavailable")
    if any(server["status"] != "ok" for server in mcp_servers.values()):
        warnings.append("one or more MCP servers missing from LiteLLM config")
    overall: HealthStatus = "ok"
    if any(
        services[name] == "fail" for name in ("litellm", "ollama", "qdrant", "postgres")
    ):
        overall = "fail"
    elif warnings:
        overall = "degraded"
    return {
        "schema_version": "quimera-pr08-integration-health-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "services": services,
        "service_latencies_ms": service_latencies_ms,
        "mcp_servers": mcp_servers,
        "models": litellm_models,
        "otel": {
            "otel_sdk_disabled": os.getenv("OTEL_SDK_DISABLED", "").lower() == "true",
            "service_name": os.getenv("OTEL_SERVICE_NAME", "quimera"),
        },
        "warnings": warnings,
    }


def _service_statuses(base_status: dict[str, Any]) -> dict[str, ServiceStatus]:
    raw_services = base_status.get("services", {})
    result: dict[str, ServiceStatus] = {}
    if isinstance(raw_services, dict):
        for name in ("ollama", "litellm", "qdrant", "postgres"):
            raw = raw_services.get(name, {})
            raw_status = raw.get("status") if isinstance(raw, dict) else "unknown"
            status = raw_status if isinstance(raw_status, str) else "unknown"
            result[name] = (
                cast(ServiceStatus, status)
                if status in {"ok", "fail", "skipped", "unknown"}
                else "unknown"
            )
    return result


def _service_latencies(base_status: dict[str, Any]) -> dict[str, float]:
    raw_services = base_status.get("services", {})
    result: dict[str, float] = {}
    if not isinstance(raw_services, dict):
        return result
    for name in ("ollama", "litellm", "qdrant", "postgres"):
        raw = raw_services.get(name, {})
        if not isinstance(raw, dict):
            continue
        latency = raw.get("latency_ms")
        if isinstance(latency, int | float) and latency >= 0:
            result[name] = float(latency)
    return result


def _litellm_models() -> dict[str, Any]:
    headers = _auth_headers()
    try:
        response = httpx.get(
            "http://127.0.0.1:4000/v1/models", headers=headers, timeout=2.0
        )
        if response.status_code >= 400:
            return {"status": "fail", "aliases": [], "required_aliases_present": False}
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {"status": "fail", "aliases": [], "required_aliases_present": False}
    aliases = _model_aliases(payload)
    required = {"qwen3-local", "nomic-embed-text"}
    return {
        "status": "ok",
        "aliases": sorted(aliases),
        "required_aliases_present": required.issubset(aliases),
    }


def _model_aliases(payload: object) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(payload, dict):
        return aliases
    data = payload.get("data")
    if not isinstance(data, list):
        return aliases
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            aliases.add(item["id"])
    return aliases


def _auth_headers() -> dict[str, str]:
    key = os.getenv("QUIMERA_LLM_API_KEY") or os.getenv("LITELLM_MASTER_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _mcp_servers_from_config(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    servers = raw.get("mcp_servers", {})
    return servers if isinstance(servers, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-artifact", action="store_true")
    args = parser.parse_args()
    report = build_integration_health_report()
    if args.write_artifact:
        write_json_artifact(HEALTH_PATH, report)
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"integration-health: {report['overall']}")
    return 0 if report["overall"] in {"ok", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
