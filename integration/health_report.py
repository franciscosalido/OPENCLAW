"""Manual weekly health report for Quimera local stack."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infra.postgres.pg_stat_report import build_report as build_pg_stat_report
from integration.check_integration_health import build_integration_health_report
from integration.report_writer import write_json_artifact
from integration.smoke_summary import BASELINE_PATH, compare_latency_baseline

HEALTH_REPORT_PATH = Path("evaluation/results/rag_01b_pr09_health_report.json")


def build_health_report() -> dict[str, Any]:
    health = build_integration_health_report()
    pg_stat = asyncio.run(build_pg_stat_report())
    backup = _latest_backup_status()
    latency = _latency_from_health(health)
    baseline = _load_baseline()
    return {
        "schema_version": "quimera-health-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "services": health.get("services", {}),
        "versions": {
            "postgres": "18.4",
            "qdrant": "1.18.x",
            "python": "3.12",
        },
        "table_sizes": {},
        "active_sessions_24h": None,
        "top_queries": pg_stat.get("top_queries", [])[:5],
        "backup": backup,
        "pg_stat_statements": pg_stat.get("pg_stat_statements", {}),
        "latency": latency,
        "baseline_comparison": compare_latency_baseline(latency, baseline, mode="quick"),
        "warnings": [*health.get("warnings", []), *pg_stat.get("warnings", [])],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Quimera Health Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Services",
        "",
    ]
    services = report.get("services", {})
    if isinstance(services, dict):
        for name, status in sorted(services.items()):
            lines.append(f"- `{name}`: `{status}`")
    lines.extend(["", "## Top Queries", ""])
    for query in report.get("top_queries", []):
        lines.append(f"- queryid `{query.get('queryid')}` mean `{query.get('mean_exec_time_ms')}` ms")
    if not report.get("top_queries"):
        lines.append("- none")
    lines.extend(["", "## Backup", "", f"- latest: `{report.get('backup', {}).get('latest_manifest')}`", f"- restore_verified: `{report.get('backup', {}).get('restore_verified')}`"])
    lines.extend(["", "## Baseline", "", f"- regressions: `{len(report.get('baseline_comparison', {}).get('regressions', []))}`"])
    return "\n".join(lines) + "\n"


def _latest_backup_status() -> dict[str, Any]:
    backup_dir = Path(".runtime/backups/postgres")
    manifests = sorted(backup_dir.glob("quimera_pg18_*.manifest.json")) if backup_dir.exists() else []
    if not manifests:
        return {"latest_manifest": None, "restore_verified": None}
    latest = manifests[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except ValueError:
        return {"latest_manifest": str(latest), "restore_verified": False}
    return {"latest_manifest": str(latest), "restore_verified": data.get("restore_verified")}


def _latency_from_health(health: dict[str, Any]) -> dict[str, float]:
    raw = health.get("service_latencies_ms", {})
    if not isinstance(raw, dict):
        return {}
    return {
        "postgres_p95_ms": float(raw.get("postgres", 0.0)),
        "qdrant_p95_ms": float(raw.get("qdrant", 0.0)),
        "litellm_p95_ms": float(raw.get("litellm", 0.0)),
        "agentic0_p95_ms": 0.0,
    }


def _load_baseline() -> dict[str, float]:
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"regression_multiplier": 2.0}
    return {key: float(value) for key, value in data.items() if isinstance(value, int | float)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--markdown", dest="markdown_path")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    report = build_health_report()
    write_json_artifact(HEALTH_REPORT_PATH, report)
    if args.json_path:
        write_json_artifact(Path(args.json_path), report)
    markdown = render_markdown(report)
    if args.markdown_path:
        path = Path(args.markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
    if args.stdout or not (args.json_path or args.markdown_path):
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
