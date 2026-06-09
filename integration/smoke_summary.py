"""PR-09 smoke summary contracts."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from integration.check_integration_health import build_integration_health_report
from integration.report_writer import write_json_artifact
from integration.run_agentic0_smoke_test import run_smoke as run_agentic0_smoke
from infra.postgres.pg_stat_report import build_report as build_pg_stat_report

SMOKE_SUMMARY_PATH = Path("evaluation/results/rag_01b_pr09_smoke_summary.json")
BASELINE_PATH = Path("baseline/rag01b_latency_baseline.json")
Mode = Literal["quick", "full", "diagnostic"]


def compare_latency_baseline(
    current: dict[str, float], baseline: dict[str, float], *, mode: str
) -> dict[str, Any]:
    multiplier = float(baseline.get("regression_multiplier", 2.0))
    regressions: list[dict[str, float | str]] = []
    for key, value in current.items():
        threshold = baseline.get(key)
        if threshold is None:
            continue
        limit = float(threshold) * multiplier
        if value > limit:
            regressions.append({"metric": key, "value": value, "limit": limit})
    return {
        "baseline_file": str(BASELINE_PATH),
        "regressions": regressions,
        "exit_code": 5 if regressions and mode in {"full", "diagnostic"} else 0,
    }


def build_smoke_summary(
    *,
    mode: Mode,
    agentic0: dict[str, Any] | None = None,
    pg_stat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    health = build_integration_health_report()
    latencies = _latencies_from_health(health)
    baseline = _load_baseline()
    comparison = compare_latency_baseline(latencies, baseline, mode=mode)
    overall = (
        "ok"
        if health["overall"] == "ok" and not comparison["regressions"]
        else "degraded"
    )
    if health["overall"] == "fail":
        overall = "degraded" if mode == "quick" else "fail"
    top_query_count = len((pg_stat or {}).get("top_queries", []))
    summary = {
        "schema_version": "quimera-pr09-smoke-summary-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "overall": overall,
        "status": overall,
        "services": {
            **health.get("services", {}),
            "mcp_postgres": {
                "status": health.get("mcp_servers", {})
                .get("quimera_postgres_memory", {})
                .get("status", "unknown")
            },
            "mcp_qdrant": {
                "status": health.get("mcp_servers", {})
                .get("quimera_qdrant_memory", {})
                .get("status", "unknown")
            },
        },
        "agentic0": agentic0
        or {"status": "skipped", "latency_ms": 0.0, "tool_calls": 0},
        "postgres": {
            "backup": {
                "created": False,
                "restore_verified": None,
                "manifest_path": None,
            },
            "pg_stat_statements": {
                "enabled": bool(
                    (pg_stat or {})
                    .get("pg_stat_statements", {})
                    .get("installed", False)
                ),
                "top_query_count": top_query_count,
            },
        },
        "latency": latencies,
        "baseline_comparison": comparison,
        "warnings": [
            *health.get("warnings", []),
            *((pg_stat or {}).get("warnings", [])),
        ],
    }
    write_json_artifact(SMOKE_SUMMARY_PATH, summary)
    return summary


async def build_smoke_summary_async(*, mode: Mode) -> dict[str, Any]:
    agentic0: dict[str, Any] | None = None
    pg_stat: dict[str, Any] | None = None
    if mode in {"full", "diagnostic"}:
        result = await run_agentic0_smoke(allow_degraded=True)
        tool_calls = len(result.tool_calls)
        agentic0 = {
            "status": "ok" if result.status == "pass" else result.status,
            "latency_ms": result.latency.total_ms,
            "tool_calls": tool_calls,
        }
        pg_stat = await build_pg_stat_report()
    return build_smoke_summary(mode=mode, agentic0=agentic0, pg_stat=pg_stat)


def render_summary_table(summary: dict[str, Any]) -> str:
    rows = [
        "| Component | Status | p50 ms | p95 ms | Notes |",
        "|-----------|--------|--------|--------|-------|",
    ]
    latency = summary.get("latency", {})
    services = summary.get("services", {})
    for component, key in (
        ("Postgres", "postgres"),
        ("Qdrant", "qdrant"),
        ("LiteLLM", "litellm"),
        ("MCP", "mcp_postgres"),
        ("Agentic0", "agentic0"),
    ):
        if component == "Agentic0":
            status = _status_from_value(summary.get("agentic0", {}))
            p95 = latency.get("agentic0_p95_ms", 0.0)
        elif component == "MCP":
            status = _status_from_value(services.get("mcp_postgres", {}))
            p95 = 0.0
        else:
            status = _status_from_value(services.get(key, {}))
            p95 = latency.get(f"{key}_p95_ms", 0.0)
        rows.append(f"| {component} | {status} | 0.0 | {p95} | local-first |")
    return "\n".join(rows)


def _status_from_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        status = value.get("status", "unknown")
        return status if isinstance(status, str) else "unknown"
    return "unknown"


def _latencies_from_health(health: dict[str, Any]) -> dict[str, float]:
    raw = health.get("service_latencies_ms", {})
    return {
        "postgres_p95_ms": float(raw.get("postgres", 0.0))
        if isinstance(raw, dict)
        else 0.0,
        "qdrant_p95_ms": float(raw.get("qdrant", 0.0))
        if isinstance(raw, dict)
        else 0.0,
        "litellm_p95_ms": float(raw.get("litellm", 0.0))
        if isinstance(raw, dict)
        else 0.0,
        "agentic0_p95_ms": 0.0,
    }


def _load_baseline() -> dict[str, float]:
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"regression_multiplier": 2.0}
    return {
        key: float(value)
        for key, value in data.items()
        if isinstance(value, int | float)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["quick", "full", "diagnostic"], default="quick"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-latency-regression", action="store_true")
    args = parser.parse_args()
    summary = asyncio.run(build_smoke_summary_async(mode=args.mode))
    regression_exit = int(summary["baseline_comparison"]["exit_code"])
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(render_summary_table(summary))
    if regression_exit == 5 and not args.allow_latency_regression:
        return 5
    if summary["overall"] == "fail":
        return 1
    if summary["overall"] == "degraded":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
